import io

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.template.loader import render_to_string
from django.contrib import messages
from django.utils.translation import gettext as _
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

from shop.models import Product, ProductVariant
from cart.cart import Cart
from .forms import OrderCreateForm
from .models import OrderItem, Order
from .tasks import order_created
from .utils import render_invoice_pdf
from .tasks import order_created, send_invoice_email_task, send_order_confirmation_email
from shop.recommender import Recommender


def order_create(request):
    """
    Path A:
    - Create order
    - Reserve for 15 minutes
    - DO NOT deduct stock
    - Deduct stock only after successful payment
    """
    cart = Cart(request)

    if cart.has_stock_issues():
        messages.error(
            request,
            _(
                "Some items in your cart exceed available stock. Please review your cart."
            ),
        )
        return redirect("cart:cart_detail")

    if request.method == "POST":
        form = OrderCreateForm(request.POST, user=request.user)

        if form.is_valid():

            # Revalidate cart stock before creating order
            revalidation = cart.revalidate_stock()
            if revalidation["changed"]:
                messages.error(
                    request,
                    _(
                        "Some items in your cart changed due to limited stock. Please review your cart."
                    ),
                )
                return redirect("cart:cart_detail")

            gateway_choice = request.POST.get("gateway", "fake")
            request.session["gateway"] = gateway_choice

            order = form.save(commit=False)
            order.payment_method = gateway_choice

            # Apply coupon
            if cart.coupon:
                order.coupon = cart.coupon
                order.discount = cart.get_discount()

            saved_address_id = form.cleaned_data.get("saved_address")
            save_address = form.cleaned_data.get("save_address")

            if saved_address_id:
                from accounts.models import Address

                address_obj = Address.objects.get(
                    id=saved_address_id, user=request.user
                )

                order = form.save(commit=False)
                order.first_name = address_obj.first_name
                order.last_name = address_obj.last_name
                order.address = address_obj.address
                order.postal_code = address_obj.postal_code
                order.city = address_obj.city
                order.user = request.user
                order.save()

            else:
                order = form.save(commit=False)
                if request.user.is_authenticated:
                    order.user = request.user
                order.save()

                # Save new address if checkbox selected
                if request.user.is_authenticated and save_address:
                    from accounts.models import Address

                    Address.objects.create(
                        user=request.user,
                        label="New Address",
                        first_name=order.first_name,
                        last_name=order.last_name,
                        address=order.address,
                        postal_code=order.postal_code,
                        city=order.city,
                    )

            order.save()

            from orders.services.events import log_order_event
            from orders.models import OrderEvent

            log_order_event(
                order,
                OrderEvent.EventType.ORDER_CREATED,
                "Order created by customer",
            )

            # ✅ Reserve stock immediately (atomic and safe)
            with transaction.atomic():
                # Phase 1: Lock and validate ALL items (variant-aware)
                items_to_reserve = []

                for item in cart:
                    variant = item.get("variant")

                    if variant:
                        # Lock variant
                        variant_obj = ProductVariant.objects.select_for_update().get(
                            pk=variant.id
                        )

                        if variant_obj.stock < item["quantity"]:
                            messages.error(
                                request,
                                _("Insufficient stock for %(product)s (%(variant)s)")
                                % {
                                    "product": item["product"].name,
                                    "variant": str(variant_obj),
                                },
                            )
                            return redirect("cart:cart_detail")

                        items_to_reserve.append(
                            ("variant", variant_obj, item["quantity"])
                        )
                    else:
                        # Lock product
                        product = Product.objects.select_for_update().get(
                            pk=item["product"].id
                        )

                        if product.stock < item["quantity"]:
                            messages.error(
                                request,
                                _("Insufficient stock for %(product)s")
                                % {"product": product.name},
                            )
                            return redirect("cart:cart_detail")

                        items_to_reserve.append(("product", product, item["quantity"]))

                # Phase 2: Deduct stock only if ALL items passed
                for item_type, obj, quantity in items_to_reserve:
                    obj.stock = F("stock") - quantity
                    obj.save(update_fields=["stock"])

            # ✅ Mark reservation
            order.reservation_status = Order.ReservationStatus.RESERVED
            order.reserved_until = timezone.now() + timedelta(minutes=15)
            order.save(update_fields=["reservation_status", "reserved_until"])

            log_order_event(
                order,
                OrderEvent.EventType.STOCK_RESERVED,
                "Stock reserved for order",
                data={
                    "reserved_until": order.reserved_until.isoformat(),
                },
            )

            # Create OrderItems only
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    product_name=item["product"].name,
                    price=item["price"],
                    quantity=item["quantity"],
                    variant=item.get("variant"),
                )

            # Send order confirmation email
            send_order_confirmation_email.delay(order.id)

            request.session["coupon_id"] = None
            cart.clear()

            request.session["order_id"] = order.id

            return redirect(reverse("payment:process", args=[order.id]))

        # If form is invalid, fall through to render with errors
        # (form already contains POST data and errors)

    else:
        # GET request - initialize form with default address if available
        initial_data = {}

        if request.user.is_authenticated:
            from accounts.models import Address

            try:
                default_address = Address.objects.get(
                    user=request.user, is_default=True
                )
                initial_data = {
                    "saved_address": default_address.id,
                    "first_name": default_address.first_name,
                    "last_name": default_address.last_name,
                    "address": default_address.address,
                    "postal_code": default_address.postal_code,
                    "city": default_address.city,
                }
            except Address.DoesNotExist:
                pass

        form = OrderCreateForm(initial=initial_data, user=request.user)

    return render(
        request,
        "orders/order/create.html",
        {
            "cart": cart,
            "form": form,
            "gateways": settings.PAYMENT_GATEWAYS,
        },
    )


@staff_member_required
def admin_order_pdf(request, order_id):
    """
    Single, clean admin view for downloading invoice PDFs.
    """
    order = get_object_or_404(Order, id=order_id)
    # This calls your xhtml2pdf utility with the correct template and context
    return render_invoice_pdf(request, "orders/pdf/invoice.html", {"order": order})


@login_required
def order_history(request):
    """Display order history for authenticated users."""
    orders = (
        Order.objects.filter(email=request.user.email)
        .prefetch_related(
            "items__product",
            "items__variant",
            "shipment",
        )
        .order_by("-created")
    )

    return render(
        request,
        "orders/order/history.html",
        {
            "orders": orders,
        },
    )


@login_required
def order_detail(request, order_id):
    """Display detailed order information with status tracking."""
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items__product",
            "items__variant",
            "events",
            "shipment",
        ),
        id=order_id,
        email=request.user.email,
    )

    return render(
        request,
        "orders/order/detail.html",
        {
            "order": order,
        },
    )
