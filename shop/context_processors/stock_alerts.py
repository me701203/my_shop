from shop.models import StockAlert


def stock_alert_count(request):
    """
    Add stock alert count to template context for authenticated users.
    """
    count = 0
    if request.user.is_authenticated:
        count = StockAlert.objects.filter(
            email=request.user.email, notified=False
        ).count()

    return {"stock_alert_count": count}
