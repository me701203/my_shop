from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    # Checkout page (you MUST keep this)
    path("create/", views.order_create, name="order_create"),
    path("history/", views.order_history, name="order_history"),
    path("<int:order_id>/", views.order_detail, name="order_detail"),
    # PDF download for the admin
    path(
        "admin/order/<int:order_id>/pdf/",
        views.admin_order_pdf,
        name="admin_order_pdf",
    ),
]
