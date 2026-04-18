from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings


class Coupon(models.Model):
    PERCENTAGE = "percentage"
    FIXED = "fixed"

    DISCOUNT_TYPES = [
        (PERCENTAGE, "Percentage"),
        (FIXED, "Fixed amount"),
    ]

    code = models.CharField(max_length=50, unique=True)

    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)

    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    # optional restrictions
    min_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    # usage control
    max_uses = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum number of times this coupon can be used.",
    )

    uses = models.PositiveIntegerField(default=0)

    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        help_text="Leave empty if coupon is valid for all users.",
    )

    active = models.BooleanField(default=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["valid_from", "valid_to"]),
        ]

    def __str__(self):
        return self.code

    def display_discount(self):
        if self.discount_type == self.PERCENTAGE:
            return f"{self.discount_value}%"
        return self.discount_value

    display_discount.short_description = "Discount"
