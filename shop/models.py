from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.core.cache import cache
from django.db.models import F, Expression

from parler.models import TranslatableModel, TranslatedFields
from parler.managers import TranslatableManager, TranslatableQuerySet


class Category(TranslatableModel):
    slug = models.SlugField(_("slug"), max_length=200, unique=True)

    translations = TranslatedFields(
        name=models.CharField(_("name"), max_length=200),
    )

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.safe_translation_getter("name", any_language=True)

    def get_absolute_url(self):
        return reverse("shop:product_list_by_category", args=[self.slug])


class AvailableProductQuerySet(TranslatableQuerySet):
    def available(self):
        return (
            self.filter(available=True)
            .filter(models.Q(stock__gt=0) | models.Q(variants__stock__gt=0))
            .distinct()
        )


class AvailableProductManager(TranslatableManager):
    def get_queryset(self):
        return AvailableProductQuerySet(self.model, using=self._db)

    def available(self):
        return self.get_queryset().available()


class Product(TranslatableModel):
    objects = TranslatableManager()  # Restore parler compatibility
    available_items = AvailableProductManager()  # our custom manager

    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.CASCADE,
        verbose_name=_("category"),
    )

    translations = TranslatedFields(
        name=models.CharField(_("name"), max_length=200),
        description=models.TextField(_("description"), blank=True),
        image_alt_text=models.CharField(
            _("image alt text"), max_length=200, blank=True
        ),
    )
    slug = models.SlugField(_("slug"), max_length=200, unique=True)
    image = models.ImageField(_("image"), upload_to="products/%Y/%m/%d", blank=True)
    price = models.DecimalField(
        _("price"),
        max_digits=20,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    available = models.BooleanField(_("available"), default=True)
    created = models.DateTimeField(_("created"), auto_now_add=True)
    updated = models.DateTimeField(_("updated"), auto_now=True)

    stock = models.PositiveIntegerField(default=0)

    meta_title = models.CharField(max_length=255, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)
    meta_keywords = models.CharField(max_length=255, blank=True, null=True)
    canonical_url = models.CharField(max_length=500, blank=True, null=True)

    og_title = models.CharField(max_length=255, blank=True, null=True)
    og_description = models.TextField(blank=True, null=True)
    og_image_alt = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["id", "slug"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["category"]),
            models.Index(fields=["available"]),
            models.Index(fields=["-created"]),
        ]

        verbose_name = _("product")
        verbose_name_plural = _("products")

    def __str__(self):
        return self.safe_translation_getter("name", any_language=True)

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.id, self.slug])

    def variant_total_stock(self):
        return sum(v.stock for v in self.variants.all())

    def save(self, *args, **kwargs):
        # 0. If product has no ID yet (first save), just save it
        if not self.pk:
            return super().save(*args, **kwargs)

        # 1. Auto availability based on variants OR product stock
        if self.variants.exists():
            total_variant_stock = sum(v.stock for v in self.variants.all())
            self.available = total_variant_stock > 0
        else:
            # Avoid evaluating F() / CombinedExpression
            if isinstance(self.stock, Expression):
                pass  # do NOT calculate availability during F() updates
            else:
                self.available = self.stock > 0

        # 2. Automatic SEO fallbacks
        if not self.meta_title:
            self.meta_title = self.safe_translation_getter("name", any_language=True)

        if not self.meta_description:
            desc = self.safe_translation_getter("description", any_language=True)
            if desc:
                self.meta_description = desc[:160]

        # 3. Automatic OG fallbacks
        if not self.og_title:
            self.og_title = self.meta_title

        if not self.og_description:
            self.og_description = self.meta_description

        if not self.og_image_alt:
            self.og_image_alt = self.safe_translation_getter(
                "image_alt_text", any_language=True
            )

        # 4. Auto canonical url
        if not self.canonical_url:
            try:
                self.canonical_url = self.get_absolute_url()
            except Exception:
                pass

        super().save(*args, **kwargs)

    def reduce_stock(self, quantity):
        from django.db import transaction

        if quantity <= 0:
            return

        with transaction.atomic():
            # Lock this row
            product = Product.objects.select_for_update().get(pk=self.pk)

            # Prevent overselling
            if product.stock < quantity:
                raise ValueError("Not enough stock available.")

            product.stock -= quantity

            # Auto-update availability
            if product.stock == 0:
                product.available = False

            product.save()

    def is_in_stock(self):
        """
        Unified stock check.
        Works whether product has variants or not.
        """
        if self.variants.exists():
            return any(v.stock > 0 for v in self.variants.all())
        return self.stock > 0


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="variants",
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )

    size = models.CharField(_("size"), max_length=50, blank=True)
    color = models.CharField(_("color"), max_length=50, blank=True)

    price_override = models.DecimalField(
        _("price override"),
        max_digits=20,
        decimal_places=2,
        blank=True,
        null=True,
        help_text=_("Optional variant-specific price"),
    )

    stock = models.PositiveIntegerField(_("stock"), default=0)

    class Meta:
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        unique_together = ("product", "size", "color")

    def __str__(self):
        name = self.product.safe_translation_getter("name", any_language=True)

        parts = []
        if self.size:
            parts.append(self.size)
        if self.color:
            parts.append(self.color)

        variant = " / ".join(parts) if parts else "Default"

        return f"{name} ({variant})"

    def get_price(self):
        return self.price_override if self.price_override else self.product.price

    def is_in_stock(self):
        return self.stock > 0

    def reduce_stock(self, quantity):
        from django.db import transaction

        if quantity <= 0:
            return

        with transaction.atomic():
            # Lock this row
            variant = ProductVariant.objects.select_for_update().get(pk=self.pk)

            # Prevent overselling
            if variant.stock < quantity:
                raise ValueError("Not enough stock available for this variant.")

            variant.stock -= quantity
            variant.save(update_fields=["stock"])


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver([post_save, post_delete], sender=Category)
def clear_category_cache(sender, **kwargs):
    cache.delete("category_sidebar")


@receiver([post_save, post_delete], sender=Product)
def clear_product_cache(sender, **kwargs):
    cache.delete("product_list_all")

    # Remove category caches
    for key in cache._cache.keys():
        if "product_list_category_" in str(key):
            cache.delete(key)


@receiver([post_save, post_delete], sender=ProductVariant)
def update_product_availability_from_variant(sender, instance, **kwargs):
    product = instance.product

    # Recalculate availability
    total_variant_stock = sum(v.stock for v in product.variants.all())
    product.available = total_variant_stock > 0

    # If product has variants, product.stock itself becomes irrelevant
    # but we do NOT modify product.stock to avoid unintended side effects.

    product.save(update_fields=["available", "updated"])

    cache.delete("product_list_all")
