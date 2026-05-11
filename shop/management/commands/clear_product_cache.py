from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = "Clear product list cache"

    def handle(self, *args, **options):
        # Clear all product list caches
        cache.delete("product_list_all")

        # Also clear category-specific caches
        from shop.models import Category

        for category in Category.objects.all():
            cache.delete(f"product_list_category_{category.slug}")

        cache.delete("category_sidebar")

        self.stdout.write(self.style.SUCCESS("Successfully cleared product list cache"))
