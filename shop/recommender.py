import redis
from django.conf import settings
from django.db.models import Count, Q, F
from .models import Product, ProductView
from datetime import timedelta
from django.utils import timezone

# connect to Redis
r = redis.Redis(host="localhost", port=6379, db=0)


class Recommender:

    def get_product_key(self, product_id):
        return f"product:{product_id}:purchased_with"

    def get_view_key(self, product_id):
        return f"product:{product_id}:viewed_with"

    def products_bought(self, products):
        """
        Update Redis sorted sets with products bought together.
        """
        product_ids = [p.id for p in products]

        for product_id in product_ids:
            for with_id in product_ids:
                if product_id != with_id:
                    r.zincrby(self.get_product_key(product_id), 1, with_id)

    def products_viewed_together(self, product_id, session_key):
        """
        Track products viewed in the same session.
        """
        session_products_key = f"session:{session_key}:products"

        # Get products viewed in this session
        viewed_products = r.smembers(session_products_key)

        # Update co-view scores
        for viewed_id in viewed_products:
            viewed_id = int(viewed_id)
            if viewed_id != product_id:
                r.zincrby(self.get_view_key(product_id), 1, viewed_id)

        # Add current product to session
        r.sadd(session_products_key, product_id)
        r.expire(session_products_key, 3600)  # Expire after 1 hour

    def suggest_products_for(self, products, max_results=4, include_views=True):
        """
        Suggest products based on purchase history and view patterns.
        """
        product_ids = [p.id for p in products]

        if len(product_ids) == 1:
            # Single product - combine purchase and view data
            purchase_suggestions = r.zrange(
                self.get_product_key(product_ids[0]), 0, -1, desc=True, withscores=True
            )

            if include_views:
                view_suggestions = r.zrange(
                    self.get_view_key(product_ids[0]), 0, -1, desc=True, withscores=True
                )

                # Combine scores (purchases weighted 3x more than views)
                combined_scores = {}
                for prod_id, score in purchase_suggestions:
                    combined_scores[int(prod_id)] = score * 3

                for prod_id, score in view_suggestions:
                    prod_id = int(prod_id)
                    combined_scores[prod_id] = combined_scores.get(prod_id, 0) + score

                # Sort by combined score
                suggestions = sorted(
                    combined_scores.items(), key=lambda x: x[1], reverse=True
                )
                suggested_ids = [
                    prod_id for prod_id, score in suggestions[:max_results]
                ]
            else:
                suggested_ids = [
                    int(prod_id)
                    for prod_id, score in purchase_suggestions[:max_results]
                ]

        else:
            # Multiple products
            flat_ids = "".join([str(id) for id in product_ids])
            tmp_key = f"tmp_{flat_ids}"

            keys = [self.get_product_key(id) for id in product_ids]

            if include_views:
                keys += [self.get_view_key(id) for id in product_ids]

            r.zunionstore(tmp_key, keys)
            r.zrem(tmp_key, *product_ids)

            suggestions = r.zrange(tmp_key, 0, -1, desc=True)[:max_results]
            suggested_ids = [int(id) for id in suggestions]
            r.delete(tmp_key)

        if not suggested_ids:
            # Fallback to trending products
            return self.get_trending_products(max_results)

        suggested_products = list(
            Product.available_items.available()
            .filter(id__in=suggested_ids)
            .select_related("category")
        )

        suggested_products.sort(key=lambda x: suggested_ids.index(x.id))

        return suggested_products

    def get_trending_products(self, max_results=4):
        """
        Get trending products based on recent views and purchases.
        """
        last_week = timezone.now() - timedelta(days=7)

        trending = (
            Product.available_items.available()
            .annotate(
                recent_views=Count(
                    "productview", filter=Q(productview__viewed_at__gte=last_week)
                )
            )
            .filter(recent_views__gt=0)
            .order_by("-recent_views", "-purchase_count")[:max_results]
        )

        return list(trending.select_related("category"))

    def get_similar_products(self, product, max_results=4):
        """
        Get similar products based on category and attributes.
        """
        similar = (
            Product.available_items.available()
            .filter(category=product.category)
            .exclude(id=product.id)
            .annotate(popularity=F("view_count") + F("purchase_count") * 3)
            .order_by("-popularity")[:max_results]
        )

        return list(similar.select_related("category"))

    def get_recently_viewed(self, session):
        """
        Get recently viewed products from session.
        """
        product_ids = session.get("recently_viewed", [])

        if not product_ids:
            return []

        products = (
            Product.available_items.available()
            .filter(id__in=product_ids)
            .select_related("category")
        )

        # Maintain order from session
        products_dict = {p.id: p for p in products}
        return [products_dict[pid] for pid in product_ids if pid in products_dict]
