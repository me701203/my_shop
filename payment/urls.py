from django.urls import path
from . import views

app_name = "payment"

urlpatterns = [
    path("process/<int:order_id>/", views.payment_process, name="process"),
    path("verify/<int:order_id>/", views.payment_verify, name="verify"),
    path("fake-bank/<int:order_id>/", views.fake_bank, name="fake_bank"),
]
