from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from parler.admin import TranslatableAdmin

from .models import Category, Product, ProductVariant


@admin.register(Category)
class CategoryAdmin(TranslatableAdmin):
    list_display = ["name", "slug"]
    search_fields = ["translations__name"]
    fields = ("name", "slug")

    def get_prepopulated_fields(self, request, obj=None):
        return {"slug": ("name",)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("size", "color", "price_override", "stock")


@admin.register(Product)
class ProductAdmin(TranslatableAdmin):
    list_display = [
        "image_preview",
        "name",
        "slug",
        "category",
        "price",
        "stock",
        "available",
        "created",
    ]

    list_filter = ["available", "created", "updated", "category"]

    search_fields = [
        "translations__name",
        "slug",
        "category__translations__name",
    ]

    autocomplete_fields = ["category"]

    inlines = [ProductVariantInline]

    list_editable = ["price", "stock", "available"]

    fieldsets = (
        (None, {"fields": ("name", "slug", "category", "price", "available", "stock")}),
        (_("Media"), {"fields": ("image", "image_alt_text")}),
        (_("Description"), {"fields": ("description",)}),
        (
            _("SEO"),
            {
                "classes": ("collapse",),
                "fields": (
                    "meta_title",
                    "meta_description",
                    "meta_keywords",
                    "canonical_url",
                    "og_title",
                    "og_description",
                    "og_image_alt",
                ),
            },
        ),
    )

    def get_prepopulated_fields(self, request, obj=None):
        return {"slug": ("name",)}

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="50" height="50" style="object-fit:cover;border-radius:4px;" />',
                obj.image.url,
            )
        return "-"

    image_preview.short_description = _("Image")
