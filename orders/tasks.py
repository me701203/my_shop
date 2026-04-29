import traceback
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from .utils import generate_invoice_pdf  # <-- IMPORTANT

from .models import Order
from shop.models import Product

logger = get_task_logger(__name__)


# ---------------------------------------------------------
# Order Created Task  (UNCHANGED)
# ---------------------------------------------------------
@shared_task
def order_created(order_id):
    order = Order.objects.get(id=order_id)
    subject = f"Order nr. {order.id}"
    message = (
        f"Dear {order.first_name},\n\n"
        f"You have successfully placed an order."
        f"Your order ID is {order.id}."
    )
    mail_sent = send_mail(subject, message, "admin@myshop.com", [order.email])
    return mail_sent


# ---------------------------------------------------------
# ASYNC Invoice Email Task (NOW USING PDF GENERATOR)
# ---------------------------------------------------------
@shared_task(bind=True, max_retries=3)
def send_invoice_email_task(self, order_id):
    """
    Generates the invoice PDF using ReportLab and emails it asynchronously.
    Retries automatically if the SMTP server fails.
    """
    try:
        order = Order.objects.get(id=order_id)

        try:
            # 1) Generate PDF bytes (ReportLab)
            pdf_bytes = generate_invoice_pdf(order)
        except Exception as e:
            logger.error(f"[Celery] PDF generation failed for order {order.id}: {e}")
            pdf_bytes = None
        # 2) Prepare email
        subject = f"فاکتور سفارش {order.id}"
        message = "مشتری گرامی، فاکتور خرید شما به این ایمیل پیوست شده است. با تشکر."

        email = EmailMessage(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [order.email],
        )

        # 3) Attach PDF exactly as in your email.py
        if pdf_bytes:
            email.attach(
                f"invoice_{order.id}.pdf",
                pdf_bytes,
                "application/pdf",
            )

        # 4) Send email
        email.send()
        logger.info(f"Invoice email sent to {order.email}")

        return f"Invoice sent to {order.email}"

    except Exception as exc:
        logger.error("Error in send_invoice_email_task:")
        logger.error(traceback.format_exc())
        raise self.retry(exc=exc, countdown=10)


from celery import shared_task
from django.utils import timezone
from django.db import transaction
from orders.models import Order


@shared_task
def expire_reserved_orders():
    """
    Restores stock for any order whose reservation period has expired and
    sets it as cancelled/expired.
    """
    now = timezone.now()
    count = 0

    # only look at still RESERVED orders (payment_status irrelevant)
    expiring_orders = Order.objects.filter(
        reservation_status=Order.ReservationStatus.RESERVED,
        reserved_until__isnull=False,
        reserved_until__lt=now,
    )

    for order in expiring_orders:
        with transaction.atomic():
            # lock row
            order = Order.objects.select_for_update().get(pk=order.pk)

            # restore stock
            for item in order.items.select_related("product"):
                Product.objects.filter(pk=item.product_id).update(
                    stock=F("stock") + item.quantity
                )

            # mark expired
            order.reservation_status = Order.ReservationStatus.EXPIRED
            order.payment_status = Order.PaymentStatus.CANCELLED
            order.save(update_fields=["reservation_status", "payment_status"])

            logger.info(
                f"[Expire] Order {order.id}: restored stock and expired reservation"
            )

            count += 1

    return f"{count} expired orders processed."
