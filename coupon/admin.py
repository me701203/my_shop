from django.contrib import admin
from django.conf import settings
from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "valid_from", "valid_to", "formatted_discount", "active"]
    list_filter = ["active", "valid_from", "valid_to"]
    search_fields = ["code"]

    def formatted_discount(self, obj):
        if obj.discount_type == obj.PERCENTAGE:
            return f"{obj.discount_value}%"
        return f"{obj.discount_value} {settings.CURRENCY_SYMBOL}"

    formatted_discount.short_description = "Discount"
