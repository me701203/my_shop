from django.core.management.base import BaseCommand
from django.contrib.postgres.search import SearchVector
from django.db.models import Value
from shop.models import Product


class Command(BaseCommand):
    help = "Update search vectors for all products"

    def handle(self, *args, **options):
        products = Product.objects.all()
        count = 0

        for product in products:
            try:
                # Get translations for this product
                name = product.safe_translation_getter("name", any_language=True) or ""
                description = (
                    product.safe_translation_getter("description", any_language=True)
                    or ""
                )

                # Combine text
                combined_text = f"{name} {description}"

                # Update search vector with Value wrapper
                product.search_vector = SearchVector(
                    Value(combined_text), config="english"
                )
                product.save(update_fields=["search_vector"])
                count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed to update product {product.id}: {str(e)}"
                    )
                )

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {count} products"))
