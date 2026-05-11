from django.urls import path
from . import views

app_name = "staff"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
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
    path("sales/", views.sales_dashboard, name="sales_dashboard"),
    path("orders/bulk/", views.bulk_order_action, name="bulk_order_action"),
    path("stock/", views.staff_stock_list, name="staff_stock_list"),
    path("stock/bulk-update/", views.bulk_stock_update, name="bulk_stock_update"),
]
