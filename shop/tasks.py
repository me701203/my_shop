from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from .models import Product, StockAlert

logger = get_task_logger(__name__)


@shared_task
def send_stock_alert_email(alert_id):
    """
    Send stock alert when product is back in stock.
    """
    try:
        alert = StockAlert.objects.select_related("product", "user").get(id=alert_id)
        product = alert.product

        subject = f"{product.name} دوباره موجود شد!"

        html_message = render_to_string(
            "shop/email/stock_alert.html",
            {
                "product": product,
                "user": alert.user,
            },
        )

        plain_message = render_to_string(
            "shop/email/stock_alert.txt",
            {
                "product": product,
                "user": alert.user,
            },
        )

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[alert.email],
            html_message=html_message,
            fail_silently=False,
        )

        # Mark as notified
        alert.notified = True
        alert.notified_at = timezone.now()
        alert.save(update_fields=["notified", "notified_at"])

        logger.info(f"Stock alert sent to {alert.email} for product {product.id}")
        return f"Stock alert sent to {alert.email}"

    except StockAlert.DoesNotExist:
        logger.error(f"StockAlert {alert_id} not found")
        return f"StockAlert {alert_id} not found"
    except Exception as e:
        logger.error(f"Error sending stock alert: {str(e)}")
        return f"Error sending email: {str(e)}"


@shared_task
def check_and_send_stock_alerts():
    """
    Periodic task to check products that are back in stock and send alerts.
    """
    from django.db.models import Q

    # Find products that are now in stock
    products_in_stock = Product.objects.filter(stock__gt=0)

    count = 0
    for product in products_in_stock:
        # Get unnotified alerts for this product
        alerts = StockAlert.objects.filter(product=product, notified=False)

        for alert in alerts:
            send_stock_alert_email.delay(alert.id)
            count += 1

    logger.info(f"Queued {count} stock alert emails")
    return f"{count} stock alerts queued"
