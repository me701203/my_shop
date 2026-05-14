import csv
import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import translation, timezone
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Count, Sum, Q, Max, F


from orders.models import Order, OrderItem, Shipment
from shop.models import Product, ProductVariant, StockAlert, StockHistory
from coupon.models import Coupon

from .decorators import staff_required
from .filters import apply_order_filters
from .invoice import generate_invoice_pdf
from .models import StaffActivityLog
from .logging import log_staff_action


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
    old_status = order.fulfillment_status
    new_status = request.POST.get("fulfillment_status")

    if new_status in Order.FulfillmentStatus.values:
        order.update_fulfillment_status(new_status)

        # Log the action
        log_staff_action(
            staff_user=request.user,
            action=StaffActivityLog.Action.ORDER_STATUS_CHANGED,
            description=f"Changed order #{order.id} fulfillment status from {old_status} to {new_status}",
            target_model="Order",
            target_id=order.id,
            metadata={
                "old_status": old_status,
                "new_status": new_status,
                "order_total": str(order.get_total_cost()),
            },
            request=request,
        )

        messages.success(request, "Fulfillment status updated.")
    else:
        messages.error(request, "Invalid status.")
    return redirect("staff:order_detail", order_id=order_id)


@staff_required
@require_POST
def update_shipment(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    shipment, created = Shipment.objects.get_or_create(order=order)

    old_tracking = shipment.tracking_code
    shipment.carrier = request.POST.get("carrier", shipment.carrier)
    shipment.tracking_code = request.POST.get("tracking_code", shipment.tracking_code)
    shipment.notes = request.POST.get("notes", shipment.notes)

    try:
        shipment.save()

        # Log the action
        log_staff_action(
            staff_user=request.user,
            action=StaffActivityLog.Action.SHIPMENT_UPDATED,
            description=f"Updated shipment for order #{order.id}",
            target_model="Shipment",
            target_id=shipment.id,
            metadata={
                "carrier": shipment.carrier,
                "tracking_code": shipment.tracking_code,
                "old_tracking": old_tracking,
            },
            request=request,
        )

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

    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.REPORT_VIEWED,
        description=f"Viewed sales dashboard ({days} days)",
        metadata={
            "report_type": "sales_dashboard",
            "days": days,
            "revenue": str(data["revenue_summary"]["revenue"]),
            "order_count": data["revenue_summary"]["order_count"],
        },
        request=request,
    )

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

        if updated > 0:
            log_staff_action(
                staff_user=request.user,
                action=StaffActivityLog.Action.ORDER_STATUS_CHANGED,
                description=f"Bulk marked {updated} orders as shipped",
                metadata={
                    "action": "mark_shipped",
                    "updated_count": updated,
                    "skipped_count": skipped,
                    "order_ids": order_ids[:50],  # Limit size
                },
                request=request,
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

        if updated > 0:
            log_staff_action(
                staff_user=request.user,
                action=StaffActivityLog.Action.ORDER_STATUS_CHANGED,
                description=f"Bulk cancelled {updated} orders",
                metadata={
                    "action": "mark_cancelled",
                    "updated_count": updated,
                    "skipped_count": skipped,
                    "order_ids": order_ids[:50],
                },
                request=request,
            )

    elif action == "export_csv":
        log_staff_action(
            staff_user=request.user,
            action=StaffActivityLog.Action.DATA_EXPORTED,
            description=f"Exported {orders.count()} orders to CSV",
            metadata={
                "export_type": "orders",
                "order_count": orders.count(),
            },
            request=request,
        )
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
    changes = []

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

    # log bulk action
    if updated_count > 0:
        log_staff_action(
            staff_user=request.user,
            action=StaffActivityLog.Action.STOCK_ADJUSTED,
            description=f"Bulk stock update: {updated_count} items adjusted",
            metadata={
                "updated_count": updated_count,
                "changes": changes[:50],
            },
            request=request,
        )

    messages.success(request, f"{updated_count} item(s) updated successfully.")
    return redirect("staff:stock_list")


@staff_required
def order_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    pdf = generate_invoice_pdf(order)

    # Log invoice generation
    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.INVOICE_GENERATED,
        description=f"Generated invoice for order #{order.id}",
        target_model="Order",
        target_id=order.id,
        request=request,
    )

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{order.id}.pdf"'
    return response


User = get_user_model()


@staff_required
def customer_list(request):
    """List all customers with order statistics"""
    search = request.GET.get("search", "")
    sort = request.GET.get("sort", "-date_joined")

    customers = User.objects.annotate(
        order_count=Count("orders"),
        total_spent=Sum(
            F("orders__items__price") * F("orders__items__quantity"),
            filter=Q(orders__payment_status=Order.PaymentStatus.SUCCESS),
        ),
        last_order_date=Max("orders__created"),
    )

    if search:
        customers = customers.filter(
            Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    # Sorting
    valid_sorts = [
        "-date_joined",
        "date_joined",
        "-total_spent",
        "total_spent",
        "-order_count",
        "order_count",
    ]
    if sort in valid_sorts:
        customers = customers.order_by(sort)

    paginator = Paginator(customers, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "search": search,
        "sort": sort,
    }
    return render(request, "staff/customers/list.html", context)


@staff_required
def customer_detail(request, user_id):
    """Detailed customer view with order history and activity"""
    customer = get_object_or_404(
        User.objects.annotate(
            order_count=Count("orders"),
            total_spent=Sum(
                F("orders__items__price") * F("orders__items__quantity"),
                filter=Q(orders__payment_status=Order.PaymentStatus.SUCCESS),
            ),
        ),
        id=user_id,
    )

    # Log customer data access
    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.CUSTOMER_VIEWED,
        description=f"Viewed customer details: {customer.email}",
        target_model="User",
        target_id=customer.id,
        metadata={
            "customer_email": customer.email,
            "order_count": customer.order_count,
        },
        request=request,
    )

    # Order history
    orders = (
        customer.orders.select_related().prefetch_related("items").order_by("-created")
    )

    # Recent activity (wishlist, reviews, etc.)
    recent_wishlist = customer.wishlist_items.select_related("product")[:5]

    # Customer lifetime stats
    successful_orders = orders.filter(payment_status=Order.PaymentStatus.SUCCESS)
    cancelled_orders = orders.filter(
        fulfillment_status=Order.FulfillmentStatus.CANCELLED
    )

    context = {
        "customer": customer,
        "orders": orders[:20],  # Recent 20 orders
        "recent_wishlist": recent_wishlist,
        "successful_orders_count": successful_orders.count(),
        "cancelled_orders_count": cancelled_orders.count(),
    }
    return render(request, "staff/customers/detail.html", context)


@staff_required
def coupon_list(request):
    """List all coupons with usage statistics"""
    status_filter = request.GET.get("status", "all")
    search = request.GET.get("search", "")

    coupons = Coupon.objects.annotate(usage_count=Count("orders")).order_by("-created")

    # Filter by status
    now = timezone.now()
    if status_filter == "active":
        coupons = coupons.filter(active=True, valid_from__lte=now, valid_to__gte=now)
    elif status_filter == "expired":
        coupons = coupons.filter(valid_to__lt=now)
    elif status_filter == "inactive":
        coupons = coupons.filter(active=False)

    if search:
        coupons = coupons.filter(code__icontains=search)

    paginator = Paginator(coupons, 30)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "status_filter": status_filter,
        "search": search,
    }
    return render(request, "staff/coupons/list.html", context)


@staff_required
def coupon_detail(request, coupon_id):
    """Detailed coupon view with usage history"""
    coupon = get_object_or_404(
        Coupon.objects.annotate(usage_count=Count("orders")), id=coupon_id
    )

    # Orders that used this coupon (get all for aggregation, then slice for display)
    all_orders = Order.objects.filter(coupon=coupon).select_related("user")

    # Calculate total discount given (before slicing)
    total_discount = all_orders.filter(
        payment_status=Order.PaymentStatus.SUCCESS
    ).aggregate(total=Sum("discount"))["total"] or Decimal("0.00")

    # Now slice for display
    orders = all_orders.order_by("-created")[:50]

    context = {
        "coupon": coupon,
        "orders": orders,
        "total_discount": total_discount,
    }
    return render(request, "staff/coupons/detail.html", context)


@staff_required
def coupon_create(request):
    """Create a new coupon"""
    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()
        discount_type = request.POST.get("discount_type", Coupon.PERCENTAGE)
        discount_value = request.POST.get("discount_value")
        valid_from = request.POST.get("valid_from", "").strip()
        valid_to = request.POST.get("valid_to", "").strip()

        # Validation
        if not code or not discount_value:
            messages.error(request, "Code and discount value are required.")
            return render(
                request, "staff/coupons/form.html", {"form_data": request.POST}
            )

        if Coupon.objects.filter(code=code).exists():
            messages.error(request, "A coupon with this code already exists.")
            return render(
                request, "staff/coupons/form.html", {"form_data": request.POST}
            )

        try:
            from django.utils.dateparse import parse_datetime

            # Parse datetime values (optional)
            valid_from_dt = None
            valid_to_dt = None

            if valid_from:
                valid_from_dt = parse_datetime(valid_from)
                if not valid_from_dt:
                    messages.error(request, "Invalid 'valid from' date format.")
                    return render(
                        request, "staff/coupons/form.html", {"form_data": request.POST}
                    )

            if valid_to:
                valid_to_dt = parse_datetime(valid_to)
                if not valid_to_dt:
                    messages.error(request, "Invalid 'valid to' date format.")
                    return render(
                        request, "staff/coupons/form.html", {"form_data": request.POST}
                    )

            # Validate date range if both are provided
            if valid_from_dt and valid_to_dt and valid_to_dt <= valid_from_dt:
                messages.error(request, "Valid to date must be after valid from date.")
                return render(
                    request, "staff/coupons/form.html", {"form_data": request.POST}
                )

            # Parse optional fields
            max_uses = request.POST.get("max_uses", "").strip()
            min_order_amount = request.POST.get("min_order_amount", "").strip()
            max_discount_amount = request.POST.get("max_discount_amount", "").strip()

            coupon = Coupon.objects.create(
                code=code,
                discount_type=discount_type,
                discount_value=Decimal(discount_value),
                active=request.POST.get("active") == "on",
                valid_from=valid_from_dt,
                valid_to=valid_to_dt,
                max_uses=int(max_uses) if max_uses else None,
                min_order_amount=(
                    Decimal(min_order_amount) if min_order_amount else None
                ),
                max_discount_amount=(
                    Decimal(max_discount_amount) if max_discount_amount else None
                ),
            )

            # Log the action
            log_staff_action(
                staff_user=request.user,
                action=StaffActivityLog.Action.COUPON_CREATED,
                description=f"Created coupon: {coupon.code} ({coupon.display_discount()} off)",
                target_model="Coupon",
                target_id=coupon.id,
                metadata={
                    "code": coupon.code,
                    "discount_type": coupon.discount_type,
                    "discount_value": str(coupon.discount_value),
                },
                request=request,
            )

            messages.success(request, f"Coupon '{code}' created successfully.")
            return redirect("staff:coupon_detail", coupon_id=coupon.id)

        except ValueError as e:
            messages.error(request, f"Invalid number format: {str(e)}")
            return render(
                request, "staff/coupons/form.html", {"form_data": request.POST}
            )
        except Exception as e:
            messages.error(request, f"Error creating coupon: {str(e)}")
            return render(
                request, "staff/coupons/form.html", {"form_data": request.POST}
            )

    return render(request, "staff/coupons/form.html")


@staff_required
def coupon_edit(request, coupon_id):
    """Edit an existing coupon"""
    coupon = get_object_or_404(Coupon, id=coupon_id)

    if request.method == "POST":
        valid_from = request.POST.get("valid_from", "").strip()
        valid_to = request.POST.get("valid_to", "").strip()

        try:
            from django.utils.dateparse import parse_datetime

            # Parse datetime values (optional)
            valid_from_dt = None
            valid_to_dt = None

            if valid_from:
                valid_from_dt = parse_datetime(valid_from)
                if not valid_from_dt:
                    messages.error(request, "Invalid 'valid from' date format.")
                    return render(
                        request, "staff/coupons/form.html", {"coupon": coupon}
                    )

            if valid_to:
                valid_to_dt = parse_datetime(valid_to)
                if not valid_to_dt:
                    messages.error(request, "Invalid 'valid to' date format.")
                    return render(
                        request, "staff/coupons/form.html", {"coupon": coupon}
                    )

            # Validate date range if both are provided
            if valid_from_dt and valid_to_dt and valid_to_dt <= valid_from_dt:
                messages.error(request, "Valid to date must be after valid from date.")
                return render(request, "staff/coupons/form.html", {"coupon": coupon})

            old_data = {
                "active": coupon.active,
                "discount_type": coupon.discount_type,
                "discount_value": str(coupon.discount_value),
                "max_uses": coupon.max_uses,
            }

            coupon.active = request.POST.get("active") == "on"
            coupon.discount_type = request.POST.get(
                "discount_type", coupon.discount_type
            )
            coupon.discount_value = Decimal(
                request.POST.get("discount_value", coupon.discount_value)
            )
            coupon.valid_from = valid_from_dt
            coupon.valid_to = valid_to_dt

            # Parse optional fields
            max_uses = request.POST.get("max_uses", "").strip()
            min_order_amount = request.POST.get("min_order_amount", "").strip()
            max_discount_amount = request.POST.get("max_discount_amount", "").strip()

            coupon.max_uses = int(max_uses) if max_uses else None
            coupon.min_order_amount = (
                Decimal(min_order_amount) if min_order_amount else None
            )
            coupon.max_discount_amount = (
                Decimal(max_discount_amount) if max_discount_amount else None
            )

            coupon.save()

            # Log the action
            log_staff_action(
                staff_user=request.user,
                action=StaffActivityLog.Action.COUPON_UPDATED,
                description=f"Updated coupon: {coupon.code}",
                target_model="Coupon",
                target_id=coupon.id,
                metadata={"old_data": old_data, "new_active": coupon.active},
                request=request,
            )

            messages.success(request, "Coupon updated successfully.")
            return redirect("staff:coupon_detail", coupon_id=coupon.id)

        except ValueError as e:
            messages.error(request, f"Invalid number format: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error updating coupon: {str(e)}")

    context = {"coupon": coupon}
    return render(request, "staff/coupons/form.html", context)


@staff_required
@require_POST
def coupon_delete(request, coupon_id):
    """Soft-delete a coupon (deactivate it)"""
    coupon = get_object_or_404(Coupon, id=coupon_id)
    code = coupon.code

    coupon.active = False
    coupon.save()

    # Log the action
    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.COUPON_DELETED,
        description=f"Deactivated coupon: {code}",
        target_model="Coupon",
        target_id=coupon.id,
        request=request,
    )

    messages.success(request, f"Coupon '{code}' has been deactivated.")
    return redirect("staff:coupon_list")


@staff_required
def low_performing_products(request):
    """Report showing products with low sales"""
    try:
        days = int(request.GET.get("days", 30))
        if days not in (7, 30, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    from .analytics import get_low_performing_products

    products = get_low_performing_products(days)

    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.REPORT_VIEWED,
        description=f"Viewed low performing products report ({days} days)",
        metadata={
            "report_type": "low_performing",
            "days": days,
            "products_count": len(products),
        },
        request=request,
    )

    context = {
        "products": products,
        "days": days,
    }
    return render(request, "staff/sales/low_performing.html", context)


@staff_required
def activity_log(request):
    """View staff activity logs"""
    action_filter = request.GET.get("action", "")
    staff_filter = request.GET.get("staff", "")

    logs = StaffActivityLog.objects.select_related("staff_user").all()

    if action_filter:
        logs = logs.filter(action=action_filter)

    if staff_filter:
        try:
            logs = logs.filter(staff_user_id=int(staff_filter))
        except (ValueError, TypeError):
            pass

    paginator = Paginator(logs, 100)
    page = paginator.get_page(request.GET.get("page"))

    # Get all staff users for filter dropdown
    staff_users = User.objects.filter(is_staff=True).order_by("email")

    context = {
        "page_obj": page,
        "action_filter": action_filter,
        "staff_filter": staff_filter,
        "action_choices": StaffActivityLog.Action.choices,
        "staff_users": staff_users,
    }
    return render(request, "staff/activity_log.html", context)


@staff_required
def export_activity_logs_csv(request):
    """Export activity logs to CSV"""

    # Log the export action
    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.DATA_EXPORTED,
        description="Exported activity logs to CSV",
        metadata={
            "export_type": "activity_logs",
            "filters": {
                "action": request.GET.get("action"),
                "staff": request.GET.get("staff"),
            },
        },
        request=request,
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="activity_logs.csv"'
    response.write("\ufeff")  # UTF-8 BOM

    writer = csv.writer(response)
    writer.writerow(["Date", "Staff Member", "Action", "Description", "IP Address"])

    # Apply same filters as the activity log view
    logs = StaffActivityLog.objects.select_related("staff_user").all()

    action_filter = request.GET.get("action")
    staff_filter = request.GET.get("staff")

    if action_filter:
        logs = logs.filter(action=action_filter)
    if staff_filter:
        try:
            logs = logs.filter(staff_user_id=int(staff_filter))
        except (ValueError, TypeError):
            pass

    for log in logs:
        writer.writerow(
            [
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                log.staff_user.get_full_name() or log.staff_user.email,
                log.get_action_display(),
                log.description,
                log.ip_address or "N/A",
            ]
        )

    return response


@staff_required
def export_customers_csv(request):
    """Export customers to CSV"""

    # Log export attempt FIRST
    customers = User.objects.annotate(
        order_count=Count("orders"),
        total_spent=Sum(
            F("orders__items__price") * F("orders__items__quantity"),
            filter=Q(orders__payment_status=Order.PaymentStatus.SUCCESS),
        ),
    )

    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.DATA_EXPORTED,
        description=f"Exported {customers.count()} customers to CSV",
        metadata={
            "export_type": "customers",
            "customer_count": customers.count(),
        },
        request=request,
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="customers.csv"'
    response.write("\ufeff")  # UTF-8 BOM

    writer = csv.writer(response)
    writer.writerow(
        ["Email", "Full Name", "Date Joined", "Total Orders", "Total Spent"]
    )

    for customer in customers:
        writer.writerow(
            [
                customer.email,
                customer.get_full_name() or "N/A",
                customer.date_joined.strftime("%Y-%m-%d"),
                customer.order_count or 0,
                f"{customer.total_spent or 0:.2f}",
            ]
        )

    return response


@staff_required
def best_sellers_report(request):
    """Report showing best-selling products"""
    try:
        days = int(request.GET.get("days", 30))
        if days not in (7, 30, 90):
            days = 30
    except (ValueError, TypeError):
        days = 30

    from datetime import timedelta
    from django.utils import timezone

    start_date = timezone.now() - timedelta(days=days)

    # Best-selling products
    best_products = (
        Product.objects.filter(
            orderitem__order__created__gte=start_date,
            orderitem__order__payment_status=Order.PaymentStatus.SUCCESS,
            orderitem__status=OrderItem.ItemStatus.ACTIVE,
        )
        .annotate(
            units_sold=Sum("orderitem__quantity"),
            revenue=Sum(F("orderitem__price") * F("orderitem__quantity")),
        )
        .order_by("-units_sold")[:20]
    )

    # Best-selling variants
    best_variants = (
        ProductVariant.objects.filter(
            orderitem__order__created__gte=start_date,
            orderitem__order__payment_status=Order.PaymentStatus.SUCCESS,
            orderitem__status=OrderItem.ItemStatus.ACTIVE,
        )
        .select_related("product")
        .annotate(
            units_sold=Sum("orderitem__quantity"),
            revenue=Sum(F("orderitem__price") * F("orderitem__quantity")),
        )
        .order_by("-units_sold")[:20]
    )

    log_staff_action(
        staff_user=request.user,
        action=StaffActivityLog.Action.REPORT_VIEWED,
        description=f"Viewed best sellers report ({days} days)",
        metadata={
            "report_type": "best_sellers",
            "days": days,
            "top_products_count": best_products.count(),
            "top_variants_count": best_variants.count(),
        },
        request=request,
    )

    context = {
        "best_products": best_products,
        "best_variants": best_variants,
        "days": days,
    }
    return render(request, "staff/sales/best_sellers.html", context)
