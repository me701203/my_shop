from orders.models import OrderEvent


def log_order_event(order, event_type, message, data=None):
    OrderEvent.objects.create(
        order=order,
        type=event_type,
        message=message,
        data=data or {},
    )
