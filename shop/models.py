from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.cache import cache
from django.db.models import (
    F,
    Expression,
    Q,
    Sum,
    Case,
    When,
    IntegerField,
    Subquery,
    OuterRef,
)
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.auth import get_user_model
from django.conf import settings

from decimal import Decimal
from parler.models import TranslatableModel, TranslatedFields
from parler.managers import TranslatableManager, TranslatableQuerySet
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill


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
        """
        Filter products that are:
        - marked as available=True
        - have stock > 0 OR at least one variant with stock > 0
        """
        return (
            self.filter(available=True)
            .filter(Q(stock__gt=0) | Q(variants__stock__gt=0))
            .distinct()
        )

    def with_stock_info(self):
        """
        Annotate products with total_stock.
        Uses subquery to avoid duplicate rows from JOIN.
        """
        # Subquery to sum variant stock for each product
        variant_stock_subquery = (
            ProductVariant.objects.filter(product=OuterRef("pk"))
            .values("product")
            .annotate(total=Sum("stock"))
            .values("total")
        )

        return self.annotate(
            computed_stock=Case(
                # If product has variants, use the subquery sum
                When(variants__isnull=False, then=Subquery(variant_stock_subquery)),
                # Otherwise use product's own stock
                default=F("stock"),
                output_field=IntegerField(),
            )
        )


class AvailableProductManager(TranslatableManager):
    def get_queryset(self):
        return AvailableProductQuerySet(self.model, using=self._db)

    def available(self):
        return self.get_queryset().available()


class Product(TranslatableModel):
    objects = TranslatableManager()
    available_items = AvailableProductManager()

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

    # Thumbnail specifications
    thumbnail_small = ImageSpecField(
        source="image",
        processors=[ResizeToFill(150, 150)],
        format="JPEG",
        options={"quality": 85},
    )

    thumbnail_medium = ImageSpecField(
        source="image",
        processors=[ResizeToFill(400, 400)],
        format="JPEG",
        options={"quality": 90},
    )

    thumbnail_large = ImageSpecField(
        source="image",
        processors=[ResizeToFill(800, 800)],
        format="JPEG",
        options={"quality": 95},
    )

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

    search_vector = SearchVectorField(null=True, blank=True)

    # Recommendation tracking fields
    view_count = models.PositiveIntegerField(
        _("view count"),
        default=0,
        help_text=_("Total number of times this product has been viewed"),
    )
    purchase_count = models.PositiveIntegerField(
        _("purchase count"),
        default=0,
        help_text=_("Total number of times this product has been purchased"),
    )
    last_purchased = models.DateTimeField(
        _("last purchased"),
        null=True,
        blank=True,
        help_text=_("Last time this product was purchased"),
    )

    class Meta:
        indexes = [
            models.Index(fields=["id", "slug"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["category"]),
            models.Index(fields=["available"]),
            models.Index(fields=["-created"]),
            models.Index(
                fields=["available", "stock"]
            ),  # Composite index for filtering
            GinIndex(fields=["search_vector"]),
            models.Index(fields=["-purchase_count"]),  # For popularity sorting
            models.Index(fields=["-view_count"]),
            models.Index(fields=["-last_purchased"]),
        ]

        verbose_name = _("product")
        verbose_name_plural = _("products")

    def __str__(self):
        return self.safe_translation_getter("name", any_language=True)

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.id, self.slug])

    def get_stock(self):
        """Get stock from variants if they exist, otherwise from product itself"""
        if self.variants.exists():
            return sum(v.stock for v in self.variants.all())
        return self.stock

    def variant_total_stock(self):
        """Cached variant stock calculation"""
        if not hasattr(self, "_variant_total_stock"):
            self._variant_total_stock = sum(v.stock for v in self.variants.all())
        return self._variant_total_stock

    @property
    def total_stock(self):
        """Total stock including variants"""
        if self.variants.exists():
            return sum(v.stock for v in self.variants.all())
        return self.stock

    def save(self, *args, **kwargs):
        # Skip auto-availability logic if this is an F() expression update
        skip_availability = kwargs.pop("skip_availability", False)

        # If product has no ID yet (first save), just save it
        if not self.pk:
            super().save(*args, **kwargs)
            return

        # Auto availability based on variants OR product stock
        if not skip_availability and not isinstance(self.stock, Expression):
            # Only check variants if we're not in the middle of a variant signal
            # (to avoid infinite recursion)
            if self.variants.exists():
                total_variant_stock = self.variant_total_stock()
                self.available = total_variant_stock > 0
            else:
                self.available = self.stock > 0

        # Automatic SEO fallbacks
        if not self.meta_title:
            self.meta_title = self.safe_translation_getter("name", any_language=True)

        if not self.meta_description:
            desc = self.safe_translation_getter("description", any_language=True)
            if desc:
                self.meta_description = desc[:160]

        # Automatic OG fallbacks
        if not self.og_title:
            self.og_title = self.meta_title

        if not self.og_description:
            self.og_description = self.meta_description

        if not self.og_image_alt:
            self.og_image_alt = self.safe_translation_getter(
                "image_alt_text", any_language=True
            )

        # Auto canonical url
        if not self.canonical_url:
            try:
                self.canonical_url = self.get_absolute_url()
            except Exception:
                pass

        super().save(*args, **kwargs)

        # Update search vector after save (so translations are available)

    #     if not isinstance(self.stock, Expression):
    #        Product.objects.filter(pk=self.pk).update(
    #           search_vector=(
    #              SearchVector("translations__name", weight="A", config="english")
    #             + SearchVector(
    #                "translations__description", weight="B", config="english"
    #           )
    #      )
    # )

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
            if product.stock == 0 and not product.variants.exists():
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


class ProductView(models.Model):
    """Track individual product view events"""

    product = models.ForeignKey(
        Product,
        related_name="product_views",
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="product_views",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("user"),
    )
    session_key = models.CharField(
        _("session key"),
        max_length=40,
        blank=True,
        help_text=_("For anonymous users"),
    )
    ip_address = models.GenericIPAddressField(
        _("IP address"),
        null=True,
        blank=True,
    )
    user_agent = models.TextField(
        _("user agent"),
        blank=True,
    )
    viewed_at = models.DateTimeField(
        _("viewed at"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("product view")
        verbose_name_plural = _("product views")
        ordering = ["-viewed_at"]
        indexes = [
            models.Index(fields=["product", "-viewed_at"]),
            models.Index(fields=["user", "-viewed_at"]),
            models.Index(fields=["session_key", "-viewed_at"]),
        ]

    def __str__(self):
        user_info = (
            self.user.username if self.user else f"Session {self.session_key[:8]}"
        )
        product_name = self.product.safe_translation_getter("name", any_language=True)
        return f"{user_info} viewed {product_name}"


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="variants",
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )

    size = models.CharField(_("size"), max_length=50, blank=True)
    color = models.CharField(_("color"), max_length=50, blank=True)

    image = models.ImageField(
        _("variant image"),
        upload_to="variants/%Y/%m/%d",
        blank=True,
        help_text=_("Optional variant-specific image"),
    )

    thumbnail_small = ImageSpecField(
        source="image",
        processors=[ResizeToFill(150, 150)],
        format="JPEG",
        options={"quality": 85},
    )

    thumbnail_medium = ImageSpecField(
        source="image",
        processors=[ResizeToFill(400, 400)],
        format="JPEG",
        options={"quality": 90},
    )

    thumbnail_large = ImageSpecField(
        source="image",
        processors=[ResizeToFill(800, 800)],
        format="JPEG",
        options={"quality": 95},
    )

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
        indexes = [
            models.Index(fields=["product", "stock"]),  # For stock queries
        ]

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
from django.core.cache import cache


def get_cache_version_key(key_type):
    """Generate cache version key"""
    return f"cache_version:{key_type}"


def increment_cache_version(key_type):
    """Increment cache version to invalidate all related caches"""
    version_key = get_cache_version_key(key_type)
    try:
        cache.incr(version_key)
    except ValueError:
        # Key doesn't exist, set it to 1
        cache.set(version_key, 1, timeout=None)


def get_cache_version(key_type):
    """Get current cache version"""
    version_key = get_cache_version_key(key_type)
    version = cache.get(version_key)
    if version is None:
        cache.set(version_key, 1, timeout=None)
        return 1
    return version


@receiver([post_save, post_delete], sender=Category)
def clear_category_cache(sender, **kwargs):
    """Clear category sidebar cache using versioning"""
    increment_cache_version("category_sidebar")


@receiver([post_save, post_delete], sender=Product)
def clear_product_cache(sender, **kwargs):
    """Clear product caches using targeted invalidation"""
    instance = kwargs.get("instance")

    # Increment version for all product lists
    increment_cache_version("product_list_all")

    # Increment version for specific category if available
    if instance and instance.category_id:
        increment_cache_version(f"product_list_category_{instance.category_id}")

    # Clear specific product detail cache
    if instance and instance.id:
        cache.delete(
            f"product_detail:{instance.id}:v{get_cache_version('product_detail')}"
        )


@receiver([post_save, post_delete], sender=ProductVariant)
def update_product_availability_from_variant(sender, instance, **kwargs):
    """
    Auto-update product availability when variant stock changes.
    Also clears relevant caches using versioning.
    """
    product = instance.product

    # Recalculate availability based on all variants
    total_variant_stock = sum(v.stock for v in product.variants.all())
    product.available = total_variant_stock > 0

    # Save without triggering availability recalculation again
    product.save(update_fields=["available", "updated"], skip_availability=True)

    # Increment cache versions
    increment_cache_version("product_list_all")
    if product.category_id:
        increment_cache_version(f"product_list_category_{product.category_id}")

    # Clear product detail cache
    cache.delete(f"product_detail:{product.id}:v{get_cache_version('product_detail')}")


class Review(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="reviews",
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reviews",
        on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    rating = models.PositiveSmallIntegerField(
        _("rating"),
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("Rating from 1 to 5 stars"),
    )
    comment = models.TextField(_("comment"), blank=True)
    created = models.DateTimeField(_("created"), auto_now_add=True)
    updated = models.DateTimeField(_("updated"), auto_now=True)
    is_verified_purchase = models.BooleanField(
        _("verified purchase"),
        default=False,
        help_text=_("User purchased this product"),
    )

    class Meta:
        verbose_name = _("review")
        verbose_name_plural = _("reviews")
        ordering = ["-created"]
        unique_together = ("product", "user")  # One review per user per product
        indexes = [
            models.Index(fields=["product", "-created"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        product_name = self.product.safe_translation_getter("name", any_language=True)
        return f"{self.user.username} - {product_name} ({self.rating}★)"


class Wishlist(models.Model):
    """User's wishlist for saving favorite products"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="wishlist_items",
        on_delete=models.CASCADE,
        verbose_name=_("user"),
    )
    product = models.ForeignKey(
        Product,
        related_name="wishlisted_by",
        on_delete=models.CASCADE,
        verbose_name=_("product"),
    )
    added_at = models.DateTimeField(
        _("added at"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("wishlist item")
        verbose_name_plural = _("wishlist items")
        unique_together = ("user", "product")  # One product per user
        ordering = ["-added_at"]
        indexes = [
            models.Index(fields=["user", "-added_at"]),
        ]

    def __str__(self):
        product_name = self.product.safe_translation_getter("name", any_language=True)
        return f"{self.user.username}'s wishlist: {product_name}"


@receiver([post_save, post_delete], sender=Review)
def clear_review_cache(sender, instance, **kwargs):
    cache.delete(
        f"product_detail:{instance.product_id}:v{get_cache_version('product_detail')}"
    )


class StockAlert(models.Model):
    """
    Track users who want to be notified when product is back in stock.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stock_alerts"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stock_alerts"
    )
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "product")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.product.name}"


class StockHistory(models.Model):
    CHANGE_REASON_CHOICES = [
        ("manual_adjustment", "Manual Adjustment"),
        ("restock", "Restock"),
        ("correction", "Correction"),
        ("damage", "Damage / Loss"),
        ("return", "Customer Return"),
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_history",
        null=True,
        blank=True,
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="stock_history",
        null=True,
        blank=True,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_changes",
    )
    quantity_before = models.IntegerField()
    quantity_after = models.IntegerField()
    reason = models.CharField(
        max_length=50,
        choices=CHANGE_REASON_CHOICES,
        default="manual_adjustment",
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Stock History"
        verbose_name_plural = "Stock Histories"

    def __str__(self):
        target = self.variant or self.product
        return f"{target} | {self.quantity_before} → {self.quantity_after} by {self.changed_by}"

    @property
    def quantity_change(self):
        return self.quantity_after - self.quantity_before
