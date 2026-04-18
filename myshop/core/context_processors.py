from django.conf import settings


def currency(request):
    return {
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "CURRENCY_CODE": settings.CURRENCY_CODE,
        "ORDER_LABELS": settings.ORDER_LABELS,
        "SHOP_LABELS": settings.SHOP_LABELS,
    }


def labels(request):
    return {
        "ORDER_LABELS": getattr(settings, "ORDER_LABELS", {}),
        "SHOP_LABELS": getattr(settings, "SHOP_LABELS", {}),
        "CURRENCY_SYMBOL": getattr(settings, "CURRENCY_SYMBOL", ""),
    }
