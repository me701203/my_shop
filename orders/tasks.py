from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings

from .models import Order
from .utils import generate_invoice_pdf  # <-- IMPORTANT
import traceback

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
