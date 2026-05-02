from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum


from payment.models import Refund, PaymentLog
from orders.models import Order, OrderItem


class RefundError(Exception):
    """Base refund error."""

    pass


class RefundNotAllowed(RefundError):
    """Refund is not allowed for this item/order/state."""

    pass


class RefundAmountError(RefundError):
    """Refund amount is invalid (too high, <= 0, etc.)."""

    pass


def complete_refund(refund: Refund):
    """
    Finalizes a refund:
    - validates all business rules (RefundGuard)
    - creates PaymentLog
    - updates refund status
    - updates order.payment_status
    """

    item = refund.order_item
    order = item.order

    # ---------------------------
    # 1) BASIC STATUS GUARDS
    # ---------------------------

    # a) Order must be financially successful or partially refunded
    if order.payment_status not in [
        Order.PaymentStatus.SUCCESS,
        Order.PaymentStatus.PARTIALLY_REFUNDED,
    ]:
        raise RefundNotAllowed("Order is not in a refundable payment status.")

    # b) Refund must be approved before completion
    if refund.status != Refund.RefundStatus.APPROVED:
        raise RefundNotAllowed("Refund must be approved before completion.")

    # c) Item must be cancelled (or returned, if you add that status later)
    if item.status != OrderItem.ItemStatus.CANCELLED:
        raise RefundNotAllowed("Item must be cancelled before refunding.")

    # ---------------------------
    # 2) AMOUNT GUARDS
    # ---------------------------
    if refund.amount <= Decimal("0.00"):
        raise RefundAmountError("Refund amount must be positive.")

    # Total amount that has already been COMPLETED refunded for this order
    total_completed_refunds = Refund.objects.filter(
        order_item__order=order,
        status=Refund.RefundStatus.COMPLETED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    order_total = order.get_original_total()

    # Don't allow over-refund
    if total_completed_refunds + refund.amount > order_total:
        raise RefundAmountError("Refund would exceed total paid amount for this order.")

    # ---------------------------
    # 3) SHIPMENT GUARD
    # ---------------------------
    # If you want to prevent refunds for shipped/delivered orders:
    if order.fulfillment_status in [
        Order.FulfillmentStatus.SHIPPED,
        Order.FulfillmentStatus.DELIVERED,
    ]:
        raise RefundNotAllowed("Refund is not allowed for shipped/delivered orders.")

    # ---------------------------
    # 4) DOUBLE-REFUND GUARD (per item)
    # ---------------------------
    # If you want to prevent more than item total from being refunded:

    item_total = item.get_cost()

    total_item_refunds = item.refunds.filter(
        status=Refund.RefundStatus.COMPLETED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    if total_item_refunds + refund.amount > item_total:
        raise RefundAmountError("Refund would exceed total amount for this order item.")

    # ---------------------------
    # 5) APPLY REFUND (atomic)
    # ---------------------------
    with transaction.atomic():

        # Payment log
        log = PaymentLog.objects.create(
            order=order,
            gateway=order.payment_method or "",
            action="refund",
            request_data={
                "order_item": item.id,
                "amount": str(refund.amount),
            },
            success=True,
            message="Refund completed",
        )

        refund.status = Refund.RefundStatus.COMPLETED
        refund.payment_log = log
        refund.processed_at = timezone.now()
        refund.save(update_fields=["status", "payment_log", "processed_at"])

        from orders.services.events import log_order_event
        from orders.models import OrderEvent

        log_order_event(
            order,
            OrderEvent.EventType.REFUND_COMPLETED,
            f"Refund completed for item {item.product_name}",
            data={
                "item_id": item.id,
                "amount": str(refund.amount),
            },
        )

        # Recalculate total refunded for order after this refund
        total_refunded = Refund.objects.filter(
            order_item__order=order,
            status=Refund.RefundStatus.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        if total_refunded >= order_total:
            order.payment_status = Order.PaymentStatus.REFUNDED
        else:
            order.payment_status = Order.PaymentStatus.PARTIALLY_REFUNDED

        order.save(update_fields=["payment_status"])
