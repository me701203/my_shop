from django.urls import path
from . import views
from .views import export_activity_logs_csv, export_customers_csv


app_name = "staff"

urlpatterns = [
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Dashboard
    path("", views.dashboard, name="dashboard"),
    # Orders
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path(
        "orders/<int:order_id>/fulfillment/",
        views.update_fulfillment,
        name="update_fulfillment",
    ),
    path(
        "orders/<int:order_id>/shipment/", views.update_shipment, name="update_shipment"
    ),
    path("orders/<int:order_id>/invoice/", views.order_invoice, name="order_invoice"),
    path("orders/bulk/", views.bulk_order_action, name="bulk_order_action"),
    # Sales & Analytics
    path("sales/", views.sales_dashboard, name="sales_dashboard"),
    path(
        "sales/low-performing/",
        views.low_performing_products,
        name="low_performing_products",
    ),
    path("sales/best-sellers/", views.best_sellers_report, name="best_sellers_report"),
    # Stock
    path("stock/", views.staff_stock_list, name="staff_stock_list"),
    path("stock/bulk-update/", views.bulk_stock_update, name="bulk_stock_update"),
    # Customers
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/<int:user_id>/", views.customer_detail, name="customer_detail"),
    # Coupons
    path("coupons/", views.coupon_list, name="coupon_list"),
    path("coupons/create/", views.coupon_create, name="coupon_create"),
    path("coupons/<int:coupon_id>/", views.coupon_detail, name="coupon_detail"),
    path("coupons/<int:coupon_id>/edit/", views.coupon_edit, name="coupon_edit"),
    path("coupons/<int:coupon_id>/delete/", views.coupon_delete, name="coupon_delete"),
    # Activity Log
    path("activity-log/", views.activity_log, name="activity_log"),
    # CSV Exports
    path("activity-logs/export/", export_activity_logs_csv, name="activity_log_export"),
    path("customers/export/", export_customers_csv, name="customer_export_csv"),
]
