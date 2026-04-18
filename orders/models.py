from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.conf import settings


class Order(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "pending", settings.ORDER_LABELS.get("payment_pending", "Pending")
        SUCCESS = "success", settings.ORDER_LABELS.get("payment_success", "Success")
        FAILED = "failed", settings.ORDER_LABELS.get("payment_failed", "Failed")
        CANCELLED = "cancelled", settings.ORDER_LABELS.get(
            "payment_cancelled", "Cancelled"
        )

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()

    address = models.CharField(max_length=250)
    postal_code = models.CharField(max_length=20)
    city = models.CharField(max_length=100)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(blank=True, null=True)

    payment_method = models.CharField(max_length=50, blank=True, null=True)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    payment_authority = models.CharField(max_length=100, blank=True, null=True)
    payment_ref_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["created"]),
        ]

    def __str__(self):
        return f"Order {self.id}"

    def get_total_cost(self):
        total = sum(item.get_cost() for item in self.items.all())
        return total - self.discount

    def payment_log_count(self):
        count = self.payment_logs.count()

        url = (
            reverse("admin:payment_paymentlog_changelist")
            + f"?order__id__exact={self.id}"
        )

        return format_html('<a href="{}">{}</a>', url, count)

    payment_log_count.short_description = "Logs"
    payment_log_count.admin_order_field = "payment_logs"

    coupon = models.ForeignKey(
        "coupon.Coupon",
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    discount = models.BigIntegerField(default=0)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        "shop.Product", related_name="order_items", on_delete=models.CASCADE
    )

    price = models.BigIntegerField()
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return str(self.id)

    def get_cost(self):
        return self.price * self.quantity
