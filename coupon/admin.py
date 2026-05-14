from django.contrib import admin
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "valid_from", "valid_to", "formatted_discount", "active"]
    list_filter = ["active", "valid_from", "valid_to"]
    search_fields = ["code"]

    # Make date fields optional in the admin form
    fields = [
        "code",
        "discount_type",
        "discount_value",
        "active",
        "valid_from",
        "valid_to",
        "max_uses",
        "min_order_amount",
        "max_discount_amount",
    ]

    # Specify which fields are not required
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Make date fields optional
        if "valid_from" in form.base_fields:
            form.base_fields["valid_from"].required = False
        if "valid_to" in form.base_fields:
            form.base_fields["valid_to"].required = False
        return form

    def formatted_discount(self, obj):
        if obj.discount_type == obj.PERCENTAGE:
            return f"{obj.discount_value}%"
        return f"{obj.discount_value} {settings.CURRENCY_SYMBOL}"

    formatted_discount.short_description = _("Discount")
