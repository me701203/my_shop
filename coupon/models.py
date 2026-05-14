from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Coupon(models.Model):
    PERCENTAGE = "percentage"
    FIXED = "fixed"

    DISCOUNT_TYPES = [
        (PERCENTAGE, _("Percentage")),
        (FIXED, _("Fixed amount")),
    ]

    code = models.CharField(_("code"), max_length=50, unique=True)

    valid_from = models.DateTimeField(_("valid from"), null=True)
    valid_to = models.DateTimeField(_("valid to"), null=True)

    discount_type = models.CharField(
        _("discount type"), max_length=20, choices=DISCOUNT_TYPES
    )

    discount_value = models.DecimalField(
        _("discount value"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    min_order_amount = models.DecimalField(
        _("minimum order amount"),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    max_discount_amount = models.DecimalField(
        _("maximum discount amount"),
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )

    max_uses = models.PositiveIntegerField(
        _("maximum uses"),
        blank=True,
        null=True,
        help_text=_("Maximum number of times this coupon can be used."),
    )

    uses = models.PositiveIntegerField(_("uses"), default=0)

    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name=_("valid users"),
        help_text=_("Leave empty if coupon is valid for all users."),
    )

    active = models.BooleanField(_("active"), default=True)

    created = models.DateTimeField(_("created"), auto_now_add=True)
    updated = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["valid_from", "valid_to"]),
        ]
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")

    def __str__(self):
        return self.code

    def display_discount(self):
        if self.discount_type == self.PERCENTAGE:
            return f"{self.discount_value}%"
        return self.discount_value

    display_discount.short_description = _("Discount")
