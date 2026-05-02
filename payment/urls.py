from django.urls import path
from . import views
from .views import create_refund

app_name = "payment"

urlpatterns = [
    path("process/<int:order_id>/", views.payment_process, name="process"),
    path("verify/<int:order_id>/", views.payment_verify, name="verify"),
    path("fake-bank/<int:order_id>/", views.fake_bank, name="fake_bank"),
    path(
        "staff/refund/<int:item_id>/",
        create_refund,
        name="create_refund",
    ),
]
