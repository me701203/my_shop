from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings

from cart.cart import Cart
from .forms import OrderCreateForm
from .models import OrderItem, Order
from .tasks import order_created
from .utils import render_invoice_pdf
from .tasks import send_invoice_email_task
from shop.recommender import Recommender


def order_create(request):
    """
    Handles checkout: Saves order, associates gateway, clears cart,
    triggers Celery task, and redirects to payment.
    """
    cart = Cart(request)

    if request.method == "POST":
        form = OrderCreateForm(request.POST)

        if form.is_valid():
            # Get gateway choice from POST, default to 'fake'
            gateway_choice = request.POST.get("gateway", "fake")
            request.session["gateway"] = gateway_choice

            order = form.save(commit=False)
            order.payment_method = gateway_choice

            # --- Apply coupon and discount BEFORE saving ---
            if cart.coupon:
                order.coupon = cart.coupon
                order.discount = cart.get_discount()

            order.save()  # <-- must always be saved

            # --- Create order items ---
            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    price=item["price"],
                    quantity=item["quantity"],
                )

            # update product recommendations
            recommender = Recommender()
            recommender.products_bought([item["product"] for item in cart])

            # --- Increase coupon usage ---
            if cart.coupon:
                cart.coupon.uses += 1
                cart.coupon.save()

            # --- Clear coupon from session ---
            request.session["coupon_id"] = None

            # Clear the cart session
            cart.clear()

            # Send invoice email (Celery async)
            send_invoice_email_task.delay(order.id)

            # Launch asynchronous task (Celery)
            order_created.delay(order.id)

            # Store order_id for the payment process
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
