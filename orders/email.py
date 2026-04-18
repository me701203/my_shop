from django.core.mail import EmailMessage
from .utils import generate_invoice_pdf
import arabic_reshaper
from bidi.algorithm import get_display
import logging

logger = logging.getLogger(__name__)


def send_invoice_email(order):
    try:
        # Generate PDF bytes
        pdf_bytes = generate_invoice_pdf(order)
    except Exception as exc:
        logger.error("Invoice PDF generation failed for order %s: %s", order.id, exc)
        pdf_bytes = None  # Continue without attachment

    subject = f"فاکتور سفارش {order.id}"
    message = "مشتری گرامی، فاکتور خرید شما به این ایمیل پیوست شده است. با تشکر."

    email = EmailMessage(
        subject,
        message,
        "no-reply@myshop.com",
        [order.email],
    )

    # Attach PDF only if it succeeded
    if pdf_bytes:
        email.attach(f"invoice_{order.id}.pdf", pdf_bytes, "application/pdf")

    email.send()
