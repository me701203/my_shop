import jdatetime
from django.contrib import admin, messages
from payment.services.refund import complete_refund, RefundError
from .models import PaymentLog, Refund


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


@admin.action(description="Approve refund")
def approve_refund(modeladmin, request, queryset):
    queryset.update(status=Refund.RefundStatus.APPROVED)


@admin.action(description="Complete selected refunds")
def complete_refund_action(modeladmin, request, queryset):
    for refund in queryset:
        try:
            complete_refund(refund)
        except RefundError as e:
            messages.error(request, f"Refund {refund.id}: {e}")
        except Exception as e:
            messages.error(request, f"Refund {refund.id}: Unexpected error: {e}")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "order",
        "order_item",
        "amount",
        "status",
        "created_at",
        "processed_at",
    )

    list_filter = ("status",)

    search_fields = ("order_item__order__id",)

    readonly_fields = ("created_at", "processed_at", "payment_log")

    actions = [approve_refund, complete_refund_action]
