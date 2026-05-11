import traceback
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail, EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from .utils import generate_invoice_pdf  # <-- IMPORTANT

from .models import Order
from shop.models import Product, ProductVariant

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

            # Restore stock with proper locking
            for item in order.items.all():
                if item.variant:
                    ProductVariant.objects.select_for_update().filter(
                        pk=item.variant_id
                    ).update(stock=F("stock") + item.quantity)
                else:
                    Product.objects.select_for_update().filter(
                        pk=item.product_id
                    ).update(stock=F("stock") + item.quantity)

            # mark expired
            order.reservation_status = Order.ReservationStatus.EXPIRED
            order.payment_status = Order.PaymentStatus.CANCELLED
            order.save(update_fields=["reservation_status", "payment_status"])

            logger.info(
                f"[Expire] Order {order.id}: restored stock and expired reservation"
            )

            count += 1

    return f"{count} expired orders processed."


@shared_task
def send_status_change_email(order_id, old_status, new_status):
    """
    Task to send email notification when order status changes.
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.translation import gettext as _
    from .models import Order

    order = Order.objects.get(id=order_id)

    subject = _("Order #%(order_id)s Status Update") % {"order_id": order.id}

    message = render_to_string(
        "orders/order/status_change_email.html",
        {
            "order": order,
            "old_status": old_status,
            "new_status": new_status,
        },
    )

    mail_sent = send_mail(subject, message, "admin@myshop.com", [order.email])

    return mail_sent


@shared_task
def send_order_confirmation_email(order_id):
    """
    Send order confirmation email to customer.
    """
    try:
        order = Order.objects.get(id=order_id)

        subject = f"تایید سفارش - #{order.id}"

        html_message = render_to_string(
            "orders/email/order_confirmation.html",
            {
                "order": order,
            },
        )

        plain_message = render_to_string(
            "orders/email/order_confirmation.txt",
            {
                "order": order,
            },
        )

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Order confirmation email sent for order {order_id}")
        return f"Email sent successfully for order {order_id}"

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return f"Order {order_id} not found"
    except Exception as e:
        logger.error(f"Error sending confirmation email: {str(e)}")
        return f"Error sending email: {str(e)}"


@shared_task
def send_shipment_notification_email(order_id, tracking_number=None):
    """
    Send shipping notification email.
    """
    try:
        order = Order.objects.get(id=order_id)

        subject = f"سفارش شما ارسال شد - #{order.id}"

        html_message = render_to_string(
            "orders/email/shipment_notification.html",
            {
                "order": order,
                "tracking_number": tracking_number,
            },
        )

        plain_message = render_to_string(
            "orders/email/shipment_notification.txt",
            {
                "order": order,
                "tracking_number": tracking_number,
            },
        )

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(f"Shipment email sent for order {order_id}")
        return f"Shipment email sent for order {order.id}"

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found")
        return f"Order {order_id} not found"
    except Exception as e:
        logger.error(f"Error sending shipment email: {str(e)}")
        return f"Error sending email: {str(e)}"
