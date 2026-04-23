from django.conf import settings


def labels(request):
    return {
        "ORDER_LABELS": getattr(settings, "ORDER_LABELS", {}),
        "SHOP_LABELS": getattr(settings, "SHOP_LABELS", {}),
        "CURRENCY_SYMBOL": getattr(settings, "CURRENCY_SYMBOL", ""),
    }
