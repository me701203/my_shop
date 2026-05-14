from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
import json


def validate_metadata_size(value):
    """Limit JSON metadata to 10KB"""
    json_str = json.dumps(value)
    max_size = 10 * 1024  # 10KB
    if len(json_str.encode("utf-8")) > max_size:
        raise ValidationError(f"Metadata too large. Maximum size is 10KB.")


def validate_metadata_structure(value):
    """Ensure metadata is a flat dictionary with string keys"""
    if not isinstance(value, dict):
        raise ValidationError("Metadata must be a dictionary.")

    # Limit nesting depth to prevent deeply nested JSON attacks
    def check_depth(obj, depth=0):
        if depth > 3:
            raise ValidationError("Metadata nesting too deep (max 3 levels).")
        if isinstance(obj, dict):
            for v in obj.values():
                check_depth(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                check_depth(item, depth + 1)

    check_depth(value)


class StaffActivityLog(models.Model):
    """Audit trail for all staff actions"""

    class Action(models.TextChoices):
        ORDER_STATUS_CHANGED = "order_status_changed", "Order Status Changed"
        SHIPMENT_UPDATED = "shipment_updated", "Shipment Updated"
        STOCK_ADJUSTED = "stock_adjusted", "Stock Adjusted"
        COUPON_CREATED = "coupon_created", "Coupon Created"
        COUPON_UPDATED = "coupon_updated", "Coupon Updated"
        COUPON_DELETED = "coupon_deleted", "Coupon Deleted"
        BULK_ACTION = "bulk_action", "Bulk Action"
        INVOICE_GENERATED = "invoice_generated", "Invoice Generated"
        REPORT_VIEWED = "report_viewed", "Report Viewed"
        CUSTOMER_VIEWED = "customer_viewed", "Customer Viewed"

    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="staff_activities",
    )
    action = models.CharField(max_length=50, choices=Action.choices)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    # Generic relation fields
    target_model = models.CharField(
        max_length=100, blank=True
    )  # e.g., "Order", "Coupon"
    target_id = models.PositiveIntegerField(null=True, blank=True)

    # Action details
    description = models.TextField()
    metadata = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_metadata_size, validate_metadata_structure],
    )  # Store before/after values, etc.

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["staff_user", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.staff_user} - {self.get_action_display()} - {self.timestamp}"
