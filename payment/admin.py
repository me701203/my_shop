from django.contrib import admin
from .models import PaymentLog


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "gateway",
        "action",
        "success",
        "created_at",
    )

    list_filter = ("gateway", "action", "success")
    search_fields = ("order__id",)
    readonly_fields = ("created_at",)
