from django.utils import timezone
from django.db.models import Sum, Count, Avg, F
from django.db.models.functions import TruncDate
from django.core.cache import cache
from datetime import timedelta, date
from decimal import Decimal

from orders.models import Order, OrderItem


CACHE_TTL = 60 * 15  # 15 minutes


def _cache_key(name: str, start, end) -> str:
    return f"dashboard:{name}:{start.date()}:{end.date()}"


def get_date_range(days: int = 30):
    end = timezone.now()
    start = end - timedelta(days=days)
    return start, end


def get_revenue_summary(start, end) -> dict:
    """Total revenue, order count, and AOV for paid orders in range."""
    key = _cache_key("revenue_summary", start, end)
    cached = cache.get(key)
    if cached is not None:
        return cached

    qs = Order.objects.filter(
        payment_status=Order.PaymentStatus.SUCCESS,
        paid_at__range=(start, end),
    )

    item_total = OrderItem.objects.filter(
        order__payment_status=Order.PaymentStatus.SUCCESS,
        order__paid_at__range=(start, end),
        status=OrderItem.ItemStatus.ACTIVE,
    ).aggregate(total=Sum(F("price") * F("quantity")))["total"] or Decimal("0.00")

    discount_total = qs.aggregate(total=Sum("discount"))["total"] or Decimal("0.00")

    revenue = item_total - discount_total
    order_count = qs.count()
    aov = (revenue / order_count) if order_count > 0 else Decimal("0.00")

    result = {
        "revenue": revenue,
        "order_count": order_count,
        "aov": aov,
    }
    cache.set(key, result, CACHE_TTL)
    return result


def get_revenue_trend(start, end) -> list[dict]:
    """Daily revenue for the given range, sorted by date ascending."""
    key = _cache_key("revenue_trend", start, end)
    cached = cache.get(key)
    if cached is not None:
        return cached

    daily_items = (
        OrderItem.objects.filter(
            order__payment_status=Order.PaymentStatus.SUCCESS,
            order__paid_at__range=(start, end),
            status=OrderItem.ItemStatus.ACTIVE,
        )
        .annotate(day=TruncDate("order__paid_at"))
        .values("day")
        .annotate(item_total=Sum(F("price") * F("quantity")))
        .order_by("day")
    )

    daily_discounts = (
        Order.objects.filter(
            payment_status=Order.PaymentStatus.SUCCESS,
            paid_at__range=(start, end),
        )
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(discount_total=Sum("discount"))
    )

    discount_map = {
        row["day"]: row["discount_total"] or Decimal("0.00") for row in daily_discounts
    }

    raw_result = [
        {
            "date": str(row["day"]),
            "revenue": float(
                row["item_total"] - discount_map.get(row["day"], Decimal("0.00"))
            ),
        }
        for row in daily_items
    ]

    result = fill_date_gaps(raw_result, start, end)

    cache.set(key, result, CACHE_TTL)
    return result


def get_top_products(start, end, limit: int = 10) -> list[dict]:
    """Top products by revenue in paid orders."""
    key = _cache_key(f"top_products_{limit}", start, end)
    cached = cache.get(key)
    if cached is not None:
        return cached

    result = list(
        OrderItem.objects.filter(
            order__payment_status=Order.PaymentStatus.SUCCESS,
            order__paid_at__range=(start, end),
            status=OrderItem.ItemStatus.ACTIVE,
        )
        .values("product_name")
        .annotate(
            units_sold=Sum("quantity"),
            revenue=Sum(F("price") * F("quantity")),
        )
        .order_by("-revenue")[:limit]
    )

    for row in result:
        row["revenue"] = float(row["revenue"])

    cache.set(key, result, CACHE_TTL)
    return result


def get_top_variants(start_date=None, end_date=None, limit=10):
    """
    Get top-selling product variants.
    Returns list of dicts with product_name, size, color, quantity, revenue.
    """
    from orders.models import OrderItem, Order
    from django.db.models import Sum, F, Q
    from decimal import Decimal

    queryset = OrderItem.objects.filter(
        status=OrderItem.ItemStatus.ACTIVE,
        order__payment_status=Order.PaymentStatus.SUCCESS,
    )

    if start_date:
        queryset = queryset.filter(order__paid_at__gte=start_date)
    if end_date:
        queryset = queryset.filter(order__paid_at__lte=end_date)

    # Group by product_name, variant size, and variant color
    # Handle cases where variant might be null (product without variants)
    results = (
        queryset.values("product_name", "variant__size", "variant__color")
        .annotate(
            total_quantity=Sum("quantity"),
            total_revenue=Sum(F("price") * F("quantity")),
        )
        .order_by("-total_quantity")[:limit]
    )

    # Format the results with a readable variant description
    formatted = []
    for item in results:
        variant_parts = []
        if item["variant__size"]:
            variant_parts.append(item["variant__size"])
        if item["variant__color"]:
            variant_parts.append(item["variant__color"])

        variant_display = " / ".join(variant_parts) if variant_parts else "No variant"

        formatted.append(
            {
                "product_name": item["product_name"],
                "variant": variant_display,
                "quantity": item["total_quantity"],
                "revenue": item["total_revenue"] or Decimal("0.00"),
            }
        )

    return formatted


def get_orders_by_fulfillment_status(start, end) -> list[dict]:
    """Order count grouped by fulfillment status in range."""
    key = _cache_key("fulfillment_status", start, end)
    cached = cache.get(key)
    if cached is not None:
        return cached

    qs = (
        Order.objects.filter(created__range=(start, end))
        .values("fulfillment_status")
        .annotate(count=Count("id"))
        .order_by("fulfillment_status")
    )

    status_labels = dict(Order.FulfillmentStatus.choices)
    result = [
        {
            "status": row["fulfillment_status"],
            "label": status_labels.get(
                row["fulfillment_status"], row["fulfillment_status"]
            ),
            "count": row["count"],
        }
        for row in qs
    ]

    cache.set(key, result, CACHE_TTL)
    return result


def get_dashboard_data(days: int = 30) -> dict:
    """Single entry point — returns all dashboard data."""
    start, end = get_date_range(days)
    return {
        "revenue_summary": get_revenue_summary(start, end),
        "revenue_trend": get_revenue_trend(start, end),
        "top_products": get_top_products(start, end),
        "top_variants": get_top_variants(start, end),
        "fulfillment_status": get_orders_by_fulfillment_status(start, end),
        "days": days,
        "start": start,
        "end": end,
    }


def fill_date_gaps(trend: list[dict], start, end) -> list[dict]:
    """Fill missing dates with 0 revenue."""
    by_date = {row["date"]: row["revenue"] for row in trend}
    result = []
    current = start.date()
    while current <= end.date():
        result.append({"date": str(current), "revenue": by_date.get(str(current), 0.0)})
        current += timedelta(days=1)
    return result
