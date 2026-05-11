from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    path("search/", views.product_search, name="product_search"),
    path("cache-stats/", views.cache_stats, name="cache_stats"),
    # Wishlist URLs
    path("wishlist/", views.wishlist_view, name="wishlist"),
    path("wishlist/add/<int:product_id>/", views.wishlist_add, name="wishlist_add"),
    path(
        "wishlist/remove/<int:product_id>/",
        views.wishlist_remove,
        name="wishlist_remove",
    ),
    path(
        "wishlist/toggle/<int:product_id>/",
        views.wishlist_toggle,
        name="wishlist_toggle",
    ),
    # Stock Alert
    path(
        "product/<int:product_id>/stock-alert/",
        views.subscribe_stock_alert,
        name="subscribe_stock_alert",
    ),
    path("stock-alerts/", views.stock_alerts_view, name="stock_alerts"),
    path(
        "stock-alerts/delete/<int:alert_id>/",
        views.delete_stock_alert,
        name="delete_stock_alert",
    ),
    # Category and Product URLs
    path(
        "<slug:category_slug>/",
        views.product_list,
        name="product_list_by_category",
    ),
    path(
        "<int:id>/<slug:slug>/",
        views.product_detail,
        name="product_detail",
    ),
]
