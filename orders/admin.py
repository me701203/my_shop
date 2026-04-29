import csv
import datetime
from django.contrib import admin
from django.http import HttpResponse
from django.urls import reverse, path
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Order, OrderItem
from .views import admin_order_pdf
from .tasks import send_invoice_email_task
import jdatetime


# -----------------------
# ADMIN ACTION: SEND INVOICE
# -----------------------
def send_invoice(modeladmin, request, queryset):
    for order in queryset:
        send_invoice_email_task.delay(order.id)

    modeladmin.message_user(
        request,
        _("Invoices successfully sent for %(count)s orders.")
        % {"count": queryset.count()},
    )


send_invoice.short_description = _("Send invoice to selected orders")


# -----------------------
# CSV EXPORT
# -----------------------
def export_to_csv(modeladmin, request, queryset):
    opts = modeladmin.model._meta
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename={opts.verbose_name}.csv"
    writer = csv.writer(response)

    fields = [
        field
        for field in opts.get_fields()
        if not field.many_to_many and not field.one_to_many
    ]

    writer.writerow([field.verbose_name for field in fields])

    for obj in queryset:
        row = []
        for field in fields:
            value = getattr(obj, field.name)
            if isinstance(value, datetime.datetime):
                value = value.strftime("%d/%m/%Y")
            row.append(value)
        writer.writerow(row)

    return response


export_to_csv.short_description = _("Export to CSV")


# -----------------------
# INLINE ITEMS
# -----------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    raw_id_fields = ["product"]
    extra = 0
    verbose_name = _("Order item")
    verbose_name_plural = _("Order items")


# -----------------------
# ORDER ADMIN
# -----------------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = [
        "id",
        "invoice_pdf_link",
        "first_name",
        "last_name",
        "email",
        "payment_status_display",
        "payment_method",
        "payment_ref_id",
        "payment_reference",
        "reservation_status",
        "reserved_until",
        "fulfillment_status",
        "total_after_discount",
        "coupon",
        "discount",
        "created",
        "created_jalali",
    ]

    list_filter = [
        "payment_status",
        "payment_method",
        "reservation_status",
        "fulfillment_status",
        "created",
    ]
    actions = [export_to_csv, send_invoice]
    inlines = [OrderItemInline]

    readonly_fields = [
        "coupon",
        "discount",
        "total_after_discount",
        "created",
        "updated",
        "reservation_status",
        "reserved_until",
        "payment_reference",
    ]

    fieldsets = (
        (
            _("Customer Information"),
            {"fields": ("first_name", "last_name", "email")},
        ),
        (
            _("Address"),
            {"fields": ("address", "postal_code", "city")},
        ),
        (
            _("Reservation Status"),
            {
                "fields": (
                    "reservation_status",
                    "reserved_until",
                ),
            },
        ),
        (
            _("Payment Information"),
            {
                "fields": (
                    "payment_method",
                    "payment_status",
                    "payment_authority",
                    "payment_ref_id",
                    "payment_reference",
                ),
            },
        ),
        (
            _("Coupon & Pricing"),
            {
                "fields": ("coupon", "discount", "total_after_discount"),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created", "updated"),
            },
        ),
        (
            _("Fulfillment"),
            {
                "fields": ("fulfillment_status",),
            },
        ),
    )

    def total_after_discount(self, obj):
        return obj.get_total_cost()

    total_after_discount.short_description = _("Total (after discount)")

    # --------------------
    # STATUS BADGE
    # --------------------
    def payment_status_display(self, obj):
        status = obj.payment_status

        color = {
            obj.PaymentStatus.SUCCESS: "green",
            obj.PaymentStatus.PENDING: "#f0ad4e",
            obj.PaymentStatus.FAILED: "#dc3545",
            obj.PaymentStatus.CANCELLED: "#6c757d",
        }.get(status, "#6c757d")

        label = obj.get_payment_status_display()

        return format_html(
            '<span style="color:white;background:{};padding:3px 8px;border-radius:6px;">{}</span>',
            color,
            label,
        )

    payment_status_display.short_description = _("Payment")

    # --------------------
    # CUSTOM ADMIN URL
    # --------------------
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:order_id>/invoice/",
                self.admin_site.admin_view(admin_order_pdf),
                name="order_invoice_pdf",
            ),
        ]
        return custom_urls + urls

    # --------------------
    # PDF DOWNLOAD LINK
    # --------------------
    def invoice_pdf_link(self, obj):
        url = reverse("admin:order_invoice_pdf", args=[obj.id])
        return format_html(
            '<a href="{}" style="color:#1e88e5; font-weight:bold;">{}</a>',
            url,
            _("Download invoice"),
        )

    invoice_pdf_link.short_description = _("PDF")

    # --------------------
    # JALALI CREATED DATE
    # --------------------
    @admin.display(description=_("Created (Jalali)"))
    def created_jalali(self, obj):
        if not obj.created:
            return "-"
        j = jdatetime.datetime.fromgregorian(datetime=obj.created)
        return j.strftime("%Y/%m/%d")
