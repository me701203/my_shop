from shop.models import Wishlist


def wishlist_count(request):
    """
    Make wishlist count and product IDs available in all templates.
    """
    if not request.user.is_authenticated:
        return {"wishlist_count": 0, "wishlist_product_ids": []}

    try:
        wishlist_items = Wishlist.objects.filter(user=request.user).select_related(
            "product"
        )
        count = wishlist_items.count()
        product_ids = list(wishlist_items.values_list("product_id", flat=True))
    except Exception:
        count = 0
        product_ids = []

    return {"wishlist_count": count, "wishlist_product_ids": product_ids}
