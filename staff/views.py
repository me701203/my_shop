import csv
import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation
from django.views.decorators.http import require_POST
from django.db import transaction

from orders.models import Order, OrderItem, Shipment
from shop.models import Product, ProductVariant, StockAlert, StockHistory

from .decorators import staff_required
from .filters import apply_order_filters


@staff_required
def dashboard(request):
    total = Order.objects.count()
    needs_attention = Order.objects.filter(
        fulfillment_status=Order.FulfillmentStatus.CONFIRMED,
        payment_status=Order.PaymentStatus.SUCCESS,
    ).count()
    ready_to_ship = Order.objects.filter(
        fulfillment_status=Order.FulfillmentStatus.PACKAGING,
        payment_status=Order.PaymentStatus.SUCCESS,
    ).count()
    problem_orders = Order.objects.filter(
        fulfillment_status=Order.FulfillmentStatus.CANCELLED
    ).count()

    context = {
        "total_orders": total,
        "needs_attention": needs_attention,
        "ready_to_ship": ready_to_ship,
        "problem_orders": problem_orders,
    }
    return render(request, "staff/dashboard.html", context)


@staff_required
def order_list(request):
    queryset = Order.objects.select_related("user").prefetch_related("items")
    queryset = apply_order_filters(queryset, request.GET)

    paginator = Paginator(queryset, 25)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "params": request.GET,
        "fulfillment_choices": Order.FulfillmentStatus.choices,
        "payment_choices": Order.PaymentStatus.choices,
    }
    return render(request, "staff/orders/list.html", context)


@staff_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product", "items__variant", "events"),
        id=order_id,
    )
    context = {
        "order": order,
        "fulfillment_choices": Order.FulfillmentStatus.choices,
        "shipment_carrier_choices": Shipment.Carrier.choices,
    }
    return render(request, "staff/orders/detail.html", context)


@staff_required
@require_POST
def update_fulfillment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    new_status = request.POST.get("fulfillment_status")
    if new_status in Order.FulfillmentStatus.values:
        order.update_fulfillment_status(new_status)
        messages.success(request, "Fulfillment status updated.")
    else:
        messages.error(request, "Invalid status.")
    return redirect("staff:order_detail", order_id=order_id)


@staff_required
@require_POST
def update_shipment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    shipment, _ = Shipment.objects.get_or_create(order=order)
    shipment.carrier = request.POST.get("carrier", shipment.carrier)
    shipment.tracking_code = request.POST.get("tracking_code", shipment.tracking_code)
    shipment.notes = request.POST.get("notes", shipment.notes)
    try:
        shipment.save()
        messages.success(request, "Shipment updated.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("staff:order_detail", order_id=order_id)


@staff_required
def sales_dashboard(request):
    try:
        days = int(request.GET.get("days", 30))
        if days not in (7, 30, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    from .analytics import get_dashboard_data

    data = get_dashboard_data(days)

    lang = translation.get_language() or "en"
    symbols = getattr(settings, "CURRENCY_SYMBOLS", {})
    currency_symbol = symbols.get(lang[:2], symbols.get("en", "$"))

    context = {
        "days": days,
        "revenue": data["revenue_summary"]["revenue"],
        "order_count": data["revenue_summary"]["order_count"],
        "aov": data["revenue_summary"]["aov"],
        "top_products": data["top_products"],
        "top_variants": data["top_variants"],
        "revenue_trend_json": json.dumps(data["revenue_trend"], cls=DjangoJSONEncoder),
        "fulfillment_status_json": json.dumps(
            data["fulfillment_status"], cls=DjangoJSONEncoder
        ),
        "start": data["start"],
        "end": data["end"],
        "currency_symbol": currency_symbol,
    }
    return render(request, "staff/sales/dashboard.html", context)


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

_BULK_SHIPPABLE = {
    Order.FulfillmentStatus.CONFIRMED,
    Order.FulfillmentStatus.PACKAGING,
}


@staff_required
@require_POST
def bulk_order_action(request):
    """
    POST params:
        action      — one of: mark_shipped | mark_cancelled | export_csv
        order_ids   — list of order PKs (checkboxes)
    """
    action = request.POST.get("action", "")
    raw_ids = request.POST.getlist("order_ids")

    # Validate IDs are integers to prevent injection
    try:
        order_ids = [int(pk) for pk in raw_ids]
    except (ValueError, TypeError):
        messages.error(request, "Invalid order selection.")
        return redirect("staff:order_list")

    if not order_ids:
        messages.warning(request, "No orders selected.")
        return redirect("staff:order_list")

    orders = Order.objects.filter(pk__in=order_ids)

    if action == "mark_shipped":
        updated = 0
        skipped = 0
        for order in orders:
            if order.fulfillment_status in _BULK_SHIPPABLE:
                order.update_fulfillment_status(Order.FulfillmentStatus.SHIPPED)
                updated += 1
            else:
                skipped += 1
        messages.success(request, f"{updated} order(s) marked as shipped.")
        if skipped:
            messages.warning(
                request,
                f"{skipped} order(s) skipped — only Confirmed or Packaging orders can be shipped.",
            )

    elif action == "mark_cancelled":
        updated = 0
        skipped = 0
        for order in orders:
            # Don't cancel already-shipped or delivered orders
            if order.fulfillment_status not in (
                Order.FulfillmentStatus.SHIPPED,
                Order.FulfillmentStatus.DELIVERED,
            ):
                order.update_fulfillment_status(Order.FulfillmentStatus.CANCELLED)
                updated += 1
            else:
                skipped += 1
        messages.success(request, f"{updated} order(s) cancelled.")
        if skipped:
            messages.warning(
                request,
                f"{skipped} order(s) skipped — shipped or delivered orders cannot be cancelled.",
            )

    elif action == "export_csv":
        return _export_orders_csv(orders)

    else:
        messages.error(request, "Unknown action.")

    return redirect("staff:order_list")


def _export_orders_csv(orders) -> HttpResponse:
    """Stream selected orders as a CSV download."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="orders_export.csv"'

    # UTF-8 BOM so Excel opens it correctly
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        [
            "Order ID",
            "Created",
            "Customer",
            "Email",
            "Payment Status",
            "Fulfillment Status",
            "Items",
            "Discount",
            "Total (est.)",
        ]
    )

    orders_qs = orders.select_related("user").prefetch_related("items")

    for order in orders_qs:
        active_items = [
            i for i in order.items.all() if i.status == OrderItem.ItemStatus.ACTIVE
        ]
        items_summary = "; ".join(
            f"{i.product_name} x{i.quantity}" for i in active_items
        )
        item_total = sum(i.price * i.quantity for i in active_items)
        total = item_total - (order.discount or Decimal("0.00"))

        writer.writerow(
            [
                order.id,
                order.created.strftime("%Y-%m-%d %H:%M"),
                order.user.get_full_name() if order.user else "Guest",
                order.user.email if order.user else "",
                order.get_payment_status_display(),
                order.get_fulfillment_status_display(),
                items_summary,
                order.discount or "0",
                f"{total:.2f}",
            ]
        )

    return response


@staff_required
def staff_stock_list(request):
    search_query = request.GET.get("search", "")
    stock_filter = request.GET.get("stock_filter", "all")

    products = (
        Product.objects.filter(available=True)
        .prefetch_related("variants")
        .order_by("id")
    )

    if search_query:
        from django.db.models import Q

        products = products.filter(
            Q(translations__name__icontains=search_query)
            | Q(slug__icontains=search_query)
        ).distinct()

    product_data = []
    low_stock_count = 0
    low_stock_threshold = 5

    for product in products:
        variants = list(product.variants.all())

        if variants:
            # Product has variants - use variant stock
            for variant in variants:
                if variant.stock <= low_stock_threshold:
                    low_stock_count += 1
            product_data.append(
                {
                    "product": product,
                    "variants": variants,
                    "has_variants": True,
                }
            )
        else:
            # Product has no variants - use product stock
            if product.stock <= low_stock_threshold:
                low_stock_count += 1
            product_data.append(
                {
                    "product": product,
                    "variants": [],
                    "has_variants": False,
                    "stock": product.stock,
                }
            )

    context = {
        "product_data": product_data,
        "low_stock_count": low_stock_count,
        "search_query": search_query,
        "stock_filter": stock_filter,
        "low_stock_threshold": low_stock_threshold,
    }

    return render(request, "staff/stock/list.html", context)


@staff_required
@require_POST
def bulk_stock_update(request):
    updated_count = 0

    with transaction.atomic():
        # Handle variant stock updates
        for key, value in request.POST.items():
            if not key.startswith("stock_variant_"):
                continue
            try:
                variant_id = int(key.split("_")[2])  # stock_variant_123
                new_stock = int(value)
                if new_stock < 0:
                    continue
            except (ValueError, IndexError):
                continue

            try:
                variant = ProductVariant.objects.select_for_update().get(pk=variant_id)
            except ProductVariant.DoesNotExist:
                continue

            if variant.stock == new_stock:
                continue

            reason = request.POST.get(
                f"reason_variant_{variant_id}", "manual_adjustment"
            )
            note = request.POST.get(f"note_variant_{variant_id}", "")

            StockHistory.objects.create(
                product=variant.product,
                variant=variant,
                changed_by=request.user,
                quantity_before=variant.stock,
                quantity_after=new_stock,
                reason=reason,
                note=note,
            )

            variant.stock = new_stock
            variant.save(update_fields=["stock"])
            updated_count += 1

            # Resolve alert if stock is back above threshold
            StockAlert.objects.filter(
                variant=variant,
                is_resolved=False,
            ).update(is_resolved=True)

        # Handle product stock updates (for products without variants)
        for key, value in request.POST.items():
            if not key.startswith("stock_product_"):
                continue
            try:
                product_id = int(key.split("_")[2])  # stock_product_456
                new_stock = int(value)
                if new_stock < 0:
                    continue
            except (ValueError, IndexError):
                continue

            try:
                product = Product.objects.select_for_update().get(pk=product_id)
            except Product.DoesNotExist:
                continue

            if product.stock == new_stock:
                continue

            reason = request.POST.get(
                f"reason_product_{product_id}", "manual_adjustment"
            )
            note = request.POST.get(f"note_product_{product_id}", "")

            StockHistory.objects.create(
                product=product,
                variant=None,  # No variant for product-level stock
                changed_by=request.user,
                quantity_before=product.stock,
                quantity_after=new_stock,
                reason=reason,
                note=note,
            )

            product.stock = new_stock

            # Auto-update availability for products without variants
            if not product.variants.exists():
                product.available = new_stock > 0
                product.save(update_fields=["stock", "available", "updated"])
            else:
                product.save(update_fields=["stock", "updated"])

            updated_count += 1

            # Resolve alert if stock is back above threshold
            StockAlert.objects.filter(
                product=product,
                is_resolved=False,
            ).update(is_resolved=True)

    messages.success(request, f"{updated_count} item(s) updated successfully.")
    return redirect("staff:stock_list")
