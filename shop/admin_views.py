from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Sum, Count, Avg, F, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta
import json

from orders.models import Order, OrderItem
from shop.models import Product, Category
from accounts.models import User


@staff_member_required
def admin_dashboard(request):
    """
    Admin dashboard with sales analytics and charts.
    """
    # Date range filter
    days = int(request.GET.get("days", 30))
    start_date = timezone.now() - timedelta(days=days)

    # Key metrics
    total_revenue = (
        Order.objects.filter(paid=True, created__gte=start_date).aggregate(
            total=Sum("total_price")
        )["total"]
        or 0
    )

    total_orders = Order.objects.filter(created__gte=start_date).count()

    total_customers = User.objects.filter(date_joined__gte=start_date).count()

    avg_order_value = (
        Order.objects.filter(paid=True, created__gte=start_date).aggregate(
            avg=Avg("total_price")
        )["avg"]
        or 0
    )

    # Daily sales chart data
    daily_sales = (
        Order.objects.filter(paid=True, created__gte=start_date)
        .annotate(date=TruncDate("created"))
        .values("date")
        .annotate(revenue=Sum("total_price"), orders=Count("id"))
        .order_by("date")
    )

    chart_dates = [item["date"].strftime("%Y-%m-%d") for item in daily_sales]
    chart_revenue = [float(item["revenue"]) for item in daily_sales]
    chart_orders = [item["orders"] for item in daily_sales]

    # Top selling products
    top_products = (
        Product.objects.annotate(
            total_sold=Sum(
                "orderitems__quantity", filter=Q(orderitems__order__paid=True)
            )
        )
        .filter(total_sold__gt=0)
        .order_by("-total_sold")[:10]
    )

    # Category performance
    category_sales = (
        Category.objects.annotate(
            revenue=Sum(
                F("products__orderitems__quantity") * F("products__orderitems__price"),
                filter=Q(products__orderitems__order__paid=True),
            ),
            total_orders=Count(
                "products__orderitems__order",
                distinct=True,
                filter=Q(products__orderitems__order__paid=True),
            ),
        )
        .filter(revenue__isnull=False)
        .order_by("-revenue")
    )

    # Recent orders
    recent_orders = (
        Order.objects.filter(created__gte=start_date)
        .select_related("user")
        .order_by("-created")[:10]
    )

    # Low stock products
    low_stock_products = (
        Product.available_items.available()
        .filter(inventory__lte=10, inventory__gt=0)
        .order_by("inventory")[:10]
    )

    # Out of stock products
    out_of_stock = Product.objects.filter(inventory=0).count()

    context = {
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_customers": total_customers,
        "avg_order_value": avg_order_value,
        "chart_dates": json.dumps(chart_dates),
        "chart_revenue": json.dumps(chart_revenue),
        "chart_orders": json.dumps(chart_orders),
        "top_products": top_products,
        "category_sales": category_sales,
        "recent_orders": recent_orders,
        "low_stock_products": low_stock_products,
        "out_of_stock": out_of_stock,
        "days": days,
    }

    return render(request, "admin/dashboard.html", context)
