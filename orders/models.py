from django.db import models
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta


class Order(models.Model):
    class FulfillmentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        PACKAGING = "packaging", _("Packaging")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")

    fulfillment_status = models.CharField(
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING,
    )

    class ReservationStatus(models.TextChoices):
        RESERVED = "reserved", _("Reserved")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")
        EXPIRED = "expired", _("Expired")

    reservation_status = models.CharField(
        max_length=20,
        choices=ReservationStatus.choices,
        default=ReservationStatus.RESERVED,
    )

    reserved_until = models.DateTimeField(null=True, blank=True)

    payment_reference = models.CharField(
        max_length=255, blank=True, null=True, unique=True
    )

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    first_name = models.CharField(_("first name"), max_length=50)
    last_name = models.CharField(_("last name"), max_length=50)
    email = models.EmailField(_("email"))

    address = models.CharField(_("address"), max_length=250)
    postal_code = models.CharField(_("postal code"), max_length=20)
    city = models.CharField(_("city"), max_length=100)

    created = models.DateTimeField(_("created"), auto_now_add=True)
    updated = models.DateTimeField(_("updated"), auto_now=True)

    paid = models.BooleanField(_("paid"), default=False)
    paid_at = models.DateTimeField(_("paid at"), blank=True, null=True)

    payment_method = models.CharField(
        _("payment method"), max_length=50, blank=True, null=True
    )

    payment_status = models.CharField(
        _("payment status"),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    payment_authority = models.CharField(
        _("payment authority"), max_length=100, blank=True, null=True
    )
    payment_ref_id = models.CharField(
        _("payment reference ID"), max_length=100, blank=True, null=True, unique=True
    )
    payment_processing = models.BooleanField(
        default=False,
        help_text=_("Prevents multiple simultaneous payment verifications"),
    )

    class Meta:
        ordering = ["-created"]
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        indexes = [
            models.Index(fields=["created"]),
        ]

    def __str__(self):
        return _("Order %(id)s") % {"id": self.id}

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

    payment_log_count.short_description = _("Logs")
    payment_log_count.admin_order_field = "payment_logs"

    coupon = models.ForeignKey(
        "coupon.Coupon",
        verbose_name=_("coupon"),
        related_name="orders",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    discount = models.DecimalField(
        _("discount"),
        max_digits=20,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
    )


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name=_("order"),
        related_name="items",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "shop.Product",
        verbose_name=_("product"),
        related_name="order_items",
        on_delete=models.CASCADE,
    )

    price = models.DecimalField(
        _("price"),
        max_digits=20,  # up to 18 digits integer + 2 decimals
        decimal_places=2,
    )

    quantity = models.PositiveIntegerField(_("quantity"), default=1)

    def __str__(self):
        return str(self.id)

    def get_cost(self):
        return self.price * self.quantity
