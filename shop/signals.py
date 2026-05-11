from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from django.db.models import Value, F
from django.utils import timezone


@receiver(post_save, sender="shop.ProductTranslation")
def update_product_search_vector(sender, instance, **kwargs):
    """Update search vector when product translation is saved"""
    from shop.models import Product

    product = instance.master

    # Get current translations
    name = product.safe_translation_getter("name", any_language=True) or ""
    description = (
        product.safe_translation_getter("description", any_language=True) or ""
    )

    # Combine text
    combined_text = f"{name} {description}"

    # Update search vector
    Product.objects.filter(pk=product.pk).update(
        search_vector=SearchVector(Value(combined_text), config="english")
    )


@receiver(post_save, sender="orders.Order")
def update_purchase_counts(sender, instance, created, **kwargs):
    """
    Update product purchase_count and last_purchased when order is completed.
    """
    from shop.models import Product

    # Only process completed/paid orders
    if instance.paid:
        for item in instance.items.select_related("product"):
            if item.product:
                Product.objects.filter(pk=item.product.pk).update(
                    purchase_count=F("purchase_count") + item.quantity,
                    last_purchased=timezone.now(),
                )
