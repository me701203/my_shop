from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.urls import reverse
from django.utils import timezone
from orders.models import Order
from django.conf import settings
from django.utils.translation import gettext as _
from django.db import transaction

from .gateways.fake import FakeGateway
from .gateways.zarinpal import ZarinpalGateway
from .gateways.zibal import ZibalGateway

from payment.models import PaymentLog
from shop.models import Product
from django.db.models import F


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

    if order.reservation_status != Order.ReservationStatus.RESERVED:
        return HttpResponse(_("This order is no longer valid."))

    if order.reserved_until and timezone.now() > order.reserved_until:
        order.reservation_status = Order.ReservationStatus.EXPIRED
        order.save(update_fields=["reservation_status"])
        return HttpResponse(_("This order reservation has expired."))

    if order.payment_status != Order.PaymentStatus.PENDING:
        return HttpResponse(_("This order payment was already processed."))

    if order.payment_authority:
        return HttpResponse(_("Payment already initiated."))

    callback_url = request.build_absolute_uri(
        reverse("payment:verify", args=[order.id])
    )

    gateway = get_gateway(request)

    success, redirect_url, authority, error = gateway.request(order, callback_url)

    PaymentLog.objects.create(
        order=order,
        gateway=request.session.get("gateway", "fake"),
        action="request",
        request_data={
            "order_id": order.id,
            "amount": str(order.get_total_cost()),
        },
        response_data={
            "authority": authority,
            "redirect_url": redirect_url,
            "error": error,
        },
        success=success,
        message=error or "",
    )

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

    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)

    # 1. IDEMPOTENCY CHECK
    if order.payment_status == Order.PaymentStatus.SUCCESS:
        return render(
            request,
            "payment/payment_status.html",
            {"status": "success", "order": order},
        )

    if order.payment_status in [
        Order.PaymentStatus.FAILED,
        Order.PaymentStatus.CANCELLED,
    ]:
        return render(
            request,
            "payment/payment_status.html",
            {"status": "failure", "order": order},
        )

    # 2. RESERVATION EXPIRY CHECK
    if order.reserved_until and timezone.now() > order.reserved_until:
        # Mark as expired & failed, but DO NOT restore stock here,
        # because your Celery expire_reserved_orders already does restoration.
        order.reservation_status = Order.ReservationStatus.EXPIRED
        order.payment_status = Order.PaymentStatus.CANCELLED
        order.save(update_fields=["reservation_status", "payment_status"])

        return render(
            request,
            "payment/payment_status.html",
            {
                "status": "failure",
                "error": _("Your reservation expired. Please place the order again."),
            },
        )

    gateway = GATEWAYS.get(order.payment_method, FakeGateway)()

    # 3. CALLBACK VALIDATION
    if not gateway.is_callback_success(request):
        order.payment_status = Order.PaymentStatus.CANCELLED
        order.save(update_fields=["payment_status"])

        PaymentLog.objects.create(
            order=order,
            gateway=order.payment_method,
            action="callback",
            request_data=request.GET.dict(),
            success=False,
            message="User cancelled payment",
        )

        return render(request, "payment/payment_status.html", {"status": "cancelled"})

    # 4. ANTI-TAMPERING
    authority = gateway.get_authority(request)
    if authority != order.payment_authority:
        return HttpResponse(_("Invalid payment callback."))

    # 5. VERIFY WITH GATEWAY
    success, ref_id, error = gateway.verify(request, order)

    if success:
        # Anti-replay
        if (
            ref_id
            and Order.objects.filter(payment_ref_id=ref_id)
            .exclude(id=order.id)
            .exists()
        ):
            return HttpResponse(
                _("Security Error: This transaction ID has already been used.")
            )

        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order.id)

            # prevent double verification
            if order.payment_processing:
                return HttpResponse(_("Payment already being processed."))

            order.payment_processing = True
            order.save(update_fields=["payment_processing"])

            # ----- STOCK LOGIC -----
            # Stock already reserved at order creation.
            # Here we only confirm payment and finalize order data.

            # Update order after stock secured
            order.paid = True
            order.payment_status = Order.PaymentStatus.SUCCESS
            order.reservation_status = Order.ReservationStatus.PAID
            order.payment_ref_id = str(ref_id)
            order.paid_at = timezone.now()
            order.payment_processing = False

            order.save(
                update_fields=[
                    "paid",
                    "payment_status",
                    "reservation_status",
                    "paid_at",
                    "payment_ref_id",
                    "payment_processing",
                ]
            )
            PaymentLog.objects.create(
                order=order,
                gateway=order.payment_method,
                action="verify",
                request_data={
                    "authority": authority,
                },
                response_data={
                    "ref_id": ref_id,
                },
                success=True,
            )

        return render(
            request,
            "payment/payment_status.html",
            {"status": "success", "order": order},
        )

    # 7. FAIL CASE
    with transaction.atomic():
        order.payment_status = Order.PaymentStatus.FAILED
        order.reservation_status = Order.ReservationStatus.FAILED
        order.payment_processing = False
        order.save(
            update_fields=["payment_status", "reservation_status", "payment_processing"]
        )

        PaymentLog.objects.create(
            order=order,
            gateway=order.payment_method,
            action="verify",
            response_data={
                "error": error,
            },
            success=False,
            message=error,
        )

    return render(
        request, "payment/payment_status.html", {"status": "failure", "error": error}
    )
