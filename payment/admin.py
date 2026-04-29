from django.contrib import admin
from .models import PaymentLog
import jdatetime


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):

    list_display = (
        "order",
        "gateway",
        "action",
        "success",
        "created_at",
        "get_created_at_jalali",  # Use the custom method here
    )

    list_filter = ("gateway", "action", "success")
    search_fields = ("order__id",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    # --------------------
    # JALALI CREATED DATE
    # --------------------
    # This method converts the UTC/Gregorian date to Jalali
    @admin.display(description="تاریخ ایجاد", ordering="created_at")
    def get_created_at_jalali(self, obj):
        if obj.created_at:
            # Convert to jalali and format as: YYYY/MM/DD HH:MM
            jalali_date = jdatetime.datetime.fromgregorian(datetime=obj.created_at)
            return jalali_date.strftime("%Y/%m/%d %H:%M")
        return "-"
