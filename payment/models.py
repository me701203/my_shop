from django.db import models
from orders.models import Order
from django.utils.translation import gettext_lazy as _
from orders.models import OrderItem
from django.utils import timezone


class PaymentLog(models.Model):

    ACTION_CHOICES = [
        ("request", "Request Payment"),
        ("verify", "Verify Payment"),
        ("callback", "Gateway Callback"),
        ("refund", "Refund"),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="payment_logs"
    )

    gateway = models.CharField(max_length=50)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)

    request_data = models.JSONField(blank=True, null=True)
    response_data = models.JSONField(blank=True, null=True)

    success = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.gateway} | {self.action} | order {self.order.id}"


class Refund(models.Model):

    class RefundStatus(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        COMPLETED = "completed", _("Completed")

    order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.CASCADE,
        related_name="refunds",
    )

    amount = models.DecimalField(max_digits=20, decimal_places=2)

    reason = models.TextField(blank=True)

    status = models.CharField(
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.REQUESTED,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    processed_at = models.DateTimeField(null=True, blank=True)

    payment_log = models.ForeignKey(
        PaymentLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        item = getattr(self, "order_item", None)
        if not item or not getattr(item, "order", None):
            return f"Refund {self.id} (Invalid Order Item)"

        return (
            f"Refund for Order {item.order.id} — "
            f"{item.product_name} (x{item.quantity})"
        )

    @property
    def order(self):
        return self.order_item.order
