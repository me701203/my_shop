from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order


class Command(BaseCommand):
    help = "Expire unpaid orders and restore stock"

    def handle(self, *args, **kwargs):

        expired_orders = Order.objects.filter(
            reservation_status=Order.ReservationStatus.RESERVED,
            reserved_until__lt=timezone.now(),
        )

        for order in expired_orders:

            for item in order.items.select_related("product", "variant"):

                if item.variant:
                    item.variant.stock += item.quantity
                    item.variant.save(update_fields=["stock"])
                else:
                    item.product.stock += item.quantity
                    item.product.save(update_fields=["stock"])

            order.reservation_status = Order.ReservationStatus.EXPIRED
            order.save(update_fields=["reservation_status"])

        self.stdout.write(f"Expired {expired_orders.count()} orders")
