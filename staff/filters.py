from orders.models import Order
from django.utils import timezone
from datetime import timedelta


def apply_order_filters(queryset, params):
    # Fulfillment status
    if status := params.get("fulfillment_status"):
        queryset = queryset.filter(fulfillment_status=status)

    # Payment status
    if payment_status := params.get("payment_status"):
        queryset = queryset.filter(payment_status=payment_status)

    # Payment method
    if method := params.get("payment_method"):
        queryset = queryset.filter(payment_method=method)

    # Date range
    if date_from := params.get("date_from"):
        queryset = queryset.filter(created__date__gte=date_from)
    if date_to := params.get("date_to"):
        queryset = queryset.filter(created__date__lte=date_to)

    # Search: order ID, email, name
    if q := params.get("q"):
        from django.db.models import Q

        queryset = queryset.filter(
            Q(id__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )

    # Quick filters
    quick = params.get("quick")
    if quick == "needs_attention":
        queryset = queryset.filter(
            fulfillment_status=Order.FulfillmentStatus.CONFIRMED,
            payment_status=Order.PaymentStatus.SUCCESS,
        )
    elif quick == "ready_to_ship":
        queryset = queryset.filter(
            fulfillment_status=Order.FulfillmentStatus.PACKAGING,
            payment_status=Order.PaymentStatus.SUCCESS,
        )
    elif quick == "completed":
        queryset = queryset.filter(fulfillment_status=Order.FulfillmentStatus.DELIVERED)
    elif quick == "problem":
        from django.db.models import Q

        queryset = queryset.filter(
            Q(payment_status=Order.PaymentStatus.FAILED)
            | Q(fulfillment_status=Order.FulfillmentStatus.CANCELLED)
        )

    # Sorting
    sort = params.get("sort", "-created")
    allowed_sorts = ["created", "-created", "get_total_cost", "-updated", "updated"]
    if sort in ["-created", "created", "-updated", "updated"]:
        queryset = queryset.order_by(sort)

    return queryset
