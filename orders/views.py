from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
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
from .tasks import send_invoice_email_task
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

    if request.method == "POST":
        form = OrderCreateForm(request.POST)

        if form.is_valid():

            # Revalidate cart stock before creating order
            if cart.revalidate_stock():
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

            order.save()

            # ✅ Reserve stock immediately (atomic and safe)
            with transaction.atomic():
                for item in cart:
                    product = Product.objects.select_for_update().get(
                        pk=item["product"].id
                    )

                    if product.stock < item["quantity"]:
                        messages.error(
                            request,
                            _(
                                "Some items are no longer available in the requested quantity."
                            ),
                        )
                        return redirect("cart:cart_detail")

                    # Temporarily reserve stock
                    product.stock = F("stock") - item["quantity"]
                    product.save(update_fields=["stock"])

            # ✅ Mark reservation
            order.reservation_status = Order.ReservationStatus.RESERVED
            order.reserved_until = timezone.now() + timedelta(minutes=15)
            order.save(update_fields=["reservation_status", "reserved_until"])

            # Create OrderItems only
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    price=item["price"],
                    quantity=item["quantity"],
                )

            # Increase coupon usage
            if cart.coupon:
                cart.coupon.uses += 1
                cart.coupon.save()

            request.session["coupon_id"] = None
            cart.clear()

            request.session["order_id"] = order.id

            return redirect(reverse("payment:process", args=[order.id]))

    else:
        form = OrderCreateForm()

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
