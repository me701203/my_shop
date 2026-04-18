from django.db import models
from orders.models import Order


class PaymentLog(models.Model):

    ACTION_CHOICES = [
        ("request", "Request Payment"),
        ("verify", "Verify Payment"),
        ("callback", "Gateway Callback"),
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
