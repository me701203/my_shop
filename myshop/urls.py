from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import include, path

from shop import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("staff/", include("staff.urls", namespace="staff")),
    path("i18n/", include("django.conf.urls.i18n")),
    path("set-digits/", views.set_digits, name="set_digits"),
    path("rosetta/", include("rosetta.urls")),
]

urlpatterns += i18n_patterns(
    path("cart/", include("cart.urls", namespace="cart")),
    path("orders/", include("orders.urls", namespace="orders")),
    path("payment/", include("payment.urls", namespace="payment")),
    path("coupon/", include("coupon.urls", namespace="coupon")),
    path("", include("shop.urls", namespace="shop")),
)


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
