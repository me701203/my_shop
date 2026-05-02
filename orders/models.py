from django.db import models, transaction
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from shop.models import ProductVariant


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
        PARTIALLY_REFUNDED = "partially_refunded", _("Partially Refunded")
        REFUNDED = "refunded", _("Refunded")

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
        total = sum(
            item.get_cost()
            for item in self.items.filter(status=OrderItem.ItemStatus.ACTIVE)
        )

        return total - self.discount

    # Used for Refund System
    def get_original_total(self):
        total = sum(item.get_cost() for item in self.items.all())
        return total - self.discount

    def get_total_refunded(self):
        from django.db.models import Sum
        from payment.models import Refund
        from decimal import Decimal

        return Refund.objects.filter(
            order_item__order=self,
            status=Refund.RefundStatus.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def get_remaining_refundable(self):
        return self.get_original_total() - self.get_total_refunded()

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
    class ItemStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        CANCELLED = "cancelled", _("Cancelled")

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

    product_name = models.CharField(
        _("product name"),
        max_length=255,
        default="",  # safe default for older rows
    )

    variant = models.ForeignKey(
        ProductVariant,
        related_name="order_items",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    price = models.DecimalField(
        _("price"),
        max_digits=20,  # up to 18 digits integer + 2 decimals
        decimal_places=2,
    )

    quantity = models.PositiveIntegerField(_("quantity"), default=1)

    status = models.CharField(
        max_length=20,
        choices=ItemStatus.choices,
        default=ItemStatus.ACTIVE,
    )

    def __str__(self):
        return str(self.id)

    def get_cost(self):
        return self.price * self.quantity

    from django.db import transaction

    def cancel(self):
        from django.db.models import F
        from shop.models import Product
        from orders.services.events import log_order_event
        from orders.models import OrderEvent, Order

        if self.order.fulfillment_status in [
            Order.FulfillmentStatus.SHIPPED,
            Order.FulfillmentStatus.DELIVERED,
        ]:
            raise ValueError("Cannot cancel items from shipped orders")

        if self.status == self.ItemStatus.CANCELLED:
            return

        with transaction.atomic():
            # restore stock first
            Product.objects.select_for_update().filter(id=self.product_id).update(
                stock=F("stock") + self.quantity
            )

            # make sure status is cancelled
            self.status = self.ItemStatus.CANCELLED
            self.save(update_fields=["status"])

            order = self.order
            # If there are no more active items, cancel the order & its reservation
            if not order.items.filter(status=self.ItemStatus.ACTIVE).exists():
                order.fulfillment_status = Order.FulfillmentStatus.CANCELLED
                order.reservation_status = Order.ReservationStatus.FAILED
                order.save(update_fields=["fulfillment_status", "reservation_status"])

        log_order_event(
            self.order,
            OrderEvent.EventType.ITEM_CANCELLED,
            f"Item '{self.product_name}' cancelled",
            data={
                "item_id": self.id,
                "product_id": self.product_id,
                "quantity": self.quantity,
            },
        )


class Shipment(models.Model):
    class Carrier(models.TextChoices):
        POST = "post", _("Post")
        TIPAX = "tipax", _("Tipax")
        COURIER = "courier", _("Courier")
        OTHER = "other", _("Other")

    order = models.OneToOneField(
        Order,
        related_name="shipment",
        on_delete=models.CASCADE,
        verbose_name=_("order"),
    )

    carrier = models.CharField(
        _("carrier"),
        max_length=50,
        choices=Carrier.choices,
        default=Carrier.POST,
    )

    tracking_code = models.CharField(
        _("tracking code"),
        max_length=100,
        blank=True,
        null=True,
    )

    shipped_at = models.DateTimeField(
        _("shipped at"),
        blank=True,
        null=True,
    )

    delivered_at = models.DateTimeField(
        _("delivered at"),
        blank=True,
        null=True,
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("shipment")
        verbose_name_plural = _("shipments")

    def __str__(self):
        return f"Shipment for Order {self.order.id}"

    def save(self, *args, **kwargs):
        from django.utils import timezone
        from orders.services.events import log_order_event
        from orders.models import OrderEvent

        # Is this a new shipment?
        is_new = self.pk is None

        # Detect old tracking before saving
        old_tracking = None
        if not is_new:
            old_tracking = (
                self.__class__.objects.filter(pk=self.pk)
                .values_list("tracking_code", flat=True)
                .first()
            )

        if self.order.payment_status != Order.PaymentStatus.SUCCESS:
            raise ValueError("Cannot create shipment for unpaid order")

        if self.tracking_code and not self.shipped_at:
            self.shipped_at = timezone.now()

        if self.order.payment_status == Order.PaymentStatus.SUCCESS:
            if self.order.fulfillment_status not in [
                Order.FulfillmentStatus.SHIPPED,
                Order.FulfillmentStatus.DELIVERED,
            ]:
                self.order.fulfillment_status = Order.FulfillmentStatus.SHIPPED
                self.order.save(update_fields=["fulfillment_status"])

        # Single save
        super().save(*args, **kwargs)

        # Log shipment creation (only once, for new shipments)
        if is_new:
            event_data = {"carrier": self.carrier}
            if self.tracking_code:
                event_data["tracking_code"] = self.tracking_code

            log_order_event(
                self.order,
                OrderEvent.EventType.SHIPMENT_CREATED,
                "Shipment created for order",
                data=event_data,
            )

        # Log tracking code addition/change
        if self.tracking_code and self.tracking_code != old_tracking:
            log_order_event(
                self.order,
                OrderEvent.EventType.TRACKING_ADDED,
                f"Tracking code added: {self.tracking_code}",
                data={"tracking_code": self.tracking_code},
            )


class OrderEvent(models.Model):

    class EventType(models.TextChoices):
        ORDER_CREATED = "order_created", "Order created"
        STOCK_RESERVED = "stock_reserved", "Stock reserved"
        PAYMENT_REQUESTED = "payment_requested", "Payment requested"
        PAYMENT_SUCCESS = "payment_success", "Payment successful"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        ITEM_CANCELLED = "item_cancelled", "Item cancelled"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        REFUND_APPROVED = "refund_approved", "Refund approved"
        REFUND_COMPLETED = "refund_completed", "Refund completed"
        SHIPMENT_CREATED = "shipment_created", "Shipment created"
        ORDER_SHIPPED = "order_shipped", "Order shipped"
        TRACKING_ADDED = "tracking_added", "Tracking added"

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="events",
    )

    type = models.CharField(
        max_length=50,
        choices=EventType.choices,
    )

    message = models.TextField()

    data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.id} - {self.type}"
