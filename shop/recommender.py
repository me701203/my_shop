import redis
from django.conf import settings
from .models import Product

# connect to Redis
r = redis.Redis(host="localhost", port=6379, db=0)


class Recommender:

    def get_product_key(self, product_id):
        return f"product:{product_id}:purchased_with"

    def products_bought(self, products):
        """
        Update Redis sorted sets with products bought together.
        """
        product_ids = [p.id for p in products]

        for product_id in product_ids:
            for with_id in product_ids:
                if product_id != with_id:
                    r.zincrby(self.get_product_key(product_id), 1, with_id)

    def suggest_products_for(self, products, max_results=4):
        """
        Suggest products based on purchase history.
        """
        product_ids = [p.id for p in products]

        if len(product_ids) == 1:
            suggestions = r.zrange(
                self.get_product_key(product_ids[0]), 0, -1, desc=True
            )[:max_results]

        else:
            flat_ids = "".join([str(id) for id in product_ids])
            tmp_key = f"tmp_{flat_ids}"

            keys = [self.get_product_key(id) for id in product_ids]

            r.zunionstore(tmp_key, keys)
            r.zrem(tmp_key, *product_ids)

            suggestions = r.zrange(tmp_key, 0, -1, desc=True)[:max_results]
            r.delete(tmp_key)

        suggested_products_ids = [int(id) for id in suggestions]

        suggested_products = list(Product.objects.filter(id__in=suggested_products_ids))

        suggested_products.sort(key=lambda x: suggested_products_ids.index(x.id))

        return suggested_products
