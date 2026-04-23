from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.urls import reverse
from django.utils import timezone
from orders.models import Order
from django.conf import settings
from django.utils.translation import gettext as _

from .gateways.fake import FakeGateway
from .gateways.zarinpal import ZarinpalGateway
from .gateways.zibal import ZibalGateway


GATEWAYS = {
    "fake": FakeGateway,
    "zarinpal": ZarinpalGateway,
    "zibal": ZibalGateway,
}


def get_gateway(request):
    choice = request.session.get("gateway", "fake")
    return GATEWAYS.get(choice, FakeGateway)()


# ---------------------------------------------------------
# PAYMENT REQUEST
# ---------------------------------------------------------


def payment_process(request, order_id):

    order = get_object_or_404(Order, id=order_id)

    callback_url = request.build_absolute_uri(
        reverse("payment:verify", args=[order.id])
    )

    gateway = get_gateway(request)

    success, redirect_url, authority, error = gateway.request(order, callback_url)

    if not success:
        return HttpResponse(_("Payment error: %(error)s") % {"error": error})

    order.payment_method = request.session.get("gateway", "fake")
    order.payment_authority = authority
    order.payment_status = Order.PaymentStatus.PENDING
    order.save(update_fields=["payment_method", "payment_authority", "payment_status"])

    return redirect(redirect_url)


# ---------------------------------------------------------
# FAKE BANK (DEV ONLY)
# ---------------------------------------------------------


def fake_bank(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    verify_url = reverse("payment:verify", args=[order_id])

    # Handle the form submission (POST)
    if request.method == "POST":
        result = request.POST.get("result")
        if result == "success":
            return redirect(f"{verify_url}?success=1&trackId={order.payment_authority}")
        elif result == "cancel":
            return redirect(f"{verify_url}?success=0&trackId={order.payment_authority}")

    # Prepare context with missing variables
    context = {
        "order": order,
        "amount": order.get_total_cost(),  # Send the amount
        "ORDER_LABELS": settings.ORDER_LABELS,  # Send the labels from settings.py
    }

    return render(request, "payment/fake_bank.html", context)


# ---------------------------------------------------------
# PAYMENT VERIFY (Unified)
# ---------------------------------------------------------


def payment_verify(request, order_id):

    order = get_object_or_404(Order, id=order_id)

    if order.payment_status in [
        Order.PaymentStatus.SUCCESS,
        Order.PaymentStatus.FAILED,
        Order.PaymentStatus.CANCELLED,
    ]:
        return render(
            request,
            "payment/payment_status.html",
            {
                "status": "success",
                "order": order,
            },
        )

    gateway = GATEWAYS.get(order.payment_method, FakeGateway)()

    # --- 1. CHECK IF USER RETURNED FROM GATEWAY ---
    if not gateway.is_callback_success(request):
        order.payment_status = Order.PaymentStatus.CANCELLED
        order.save(update_fields=["payment_status"])
        return render(
            request,
            "payment/payment_status.html",
            {
                "status": "cancelled",
            },
        )

    # --- 2. ANTI‑TAMPERING ---
    authority = gateway.get_authority(request)
    if authority != order.payment_authority:
        return HttpResponse(_("Invalid payment callback."))

    # --- 3. VERIFY WITH GATEWAY ---
    success, ref_id, error = gateway.verify(request, order)

    if success:
        order.paid = True
        order.payment_status = Order.PaymentStatus.SUCCESS
        order.paid_at = timezone.now()
        order.payment_ref_id = ref_id
        order.save(
            update_fields=["paid", "payment_status", "paid_at", "payment_ref_id"]
        )
        return render(
            request,
            "payment/payment_status.html",
            {
                "status": "success",
                "order": order,
            },
        )

    # --- 4. FAIL CASE ---
    order.payment_status = Order.PaymentStatus.FAILED
    order.save(update_fields=["payment_status"])
    return render(
        request,
        "payment/payment_status.html",
        {
            "status": "failure",
            "error": error,
        },
    )
