from shop.recommender import Recommender


def recently_viewed(request):
    """
    Add recently viewed products to all templates.
    """
    recommender = Recommender()
    recently_viewed_products = recommender.get_recently_viewed(request.session)

    return {"recently_viewed_products": recently_viewed_products[:5]}  # Show max 5
