from django.core.management.base import BaseCommand
from django.utils import timezone
from shop.tasks import check_and_send_stock_alerts


class Command(BaseCommand):
    help = "Check stock and send alerts for products that are back in stock"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Checking stock alerts..."))

        result = check_and_send_stock_alerts()

        self.stdout.write(self.style.SUCCESS(f"✓ {result}"))
