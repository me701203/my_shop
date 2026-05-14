from .models import StaffActivityLog


def log_staff_action(
    staff_user,
    action,
    description,
    target_model=None,
    target_id=None,
    metadata=None,
    request=None,
):
    """
    Centralized logging function for staff actions.

    Usage:
        log_staff_action(
            staff_user=request.user,
            action=StaffActivityLog.Action.ORDER_STATUS_CHANGED,
            description=f"Changed order #{order.id} status to {new_status}",
            target_model="Order",
            target_id=order.id,
            metadata={"old_status": old_status, "new_status": new_status},
            request=request
        )
    """
    ip_address = None
    if request:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(",")[0]
        else:
            ip_address = request.META.get("REMOTE_ADDR")

    StaffActivityLog.objects.create(
        staff_user=staff_user,
        action=action,
        description=description,
        target_model=target_model or "",
        target_id=target_id,
        metadata=metadata or {},
        ip_address=ip_address,
    )
