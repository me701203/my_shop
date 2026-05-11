import time
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)


class CacheMonitoringMiddleware(MiddlewareMixin):
    """Monitor cache hit rates and performance"""

    STATS_KEY = "cache_stats"

    def process_request(self, request):
        request._cache_start_time = time.time()
        request._cache_hits_before = self.get_stats().get("hits", 0)
        request._cache_misses_before = self.get_stats().get("misses", 0)

    def process_response(self, request, response):
        if not hasattr(request, "_cache_start_time"):
            return response

        # Calculate request time
        request_time = time.time() - request._cache_start_time

        # Get cache stats change during this request
        stats = self.get_stats()
        hits_during = stats.get("hits", 0) - request._cache_hits_before
        misses_during = stats.get("misses", 0) - request._cache_misses_before

        # Add headers for debugging (remove in production or restrict by IP)
        if request.user.is_staff or request.GET.get("debug_cache"):
            response["X-Cache-Hits"] = hits_during
            response["X-Cache-Misses"] = misses_during
            response["X-Request-Time"] = f"{request_time:.3f}s"

            if hits_during + misses_during > 0:
                hit_rate = (hits_during / (hits_during + misses_during)) * 100
                response["X-Cache-Hit-Rate"] = f"{hit_rate:.1f}%"

        return response

    @classmethod
    def get_stats(cls):
        """Get current cache statistics"""
        stats = cache.get(cls.STATS_KEY)
        if stats is None:
            stats = {"hits": 0, "misses": 0, "sets": 0}
            cache.set(cls.STATS_KEY, stats, timeout=None)
        return stats

    @classmethod
    def record_hit(cls):
        """Record a cache hit"""
        stats = cls.get_stats()
        stats["hits"] = stats.get("hits", 0) + 1
        cache.set(cls.STATS_KEY, stats, timeout=None)

    @classmethod
    def record_miss(cls):
        """Record a cache miss"""
        stats = cls.get_stats()
        stats["misses"] = stats.get("misses", 0) + 1
        cache.set(cls.STATS_KEY, stats, timeout=None)

    @classmethod
    def record_set(cls):
        """Record a cache set operation"""
        stats = cls.get_stats()
        stats["sets"] = stats.get("sets", 0) + 1
        cache.set(cls.STATS_KEY, stats, timeout=None)

    @classmethod
    def reset_stats(cls):
        """Reset cache statistics"""
        cache.delete(cls.STATS_KEY)

    @classmethod
    def get_hit_rate(cls):
        """Calculate cache hit rate percentage"""
        stats = cls.get_stats()
        hits = stats.get("hits", 0)
        misses = stats.get("misses", 0)
        total = hits + misses

        if total == 0:
            return 0.0

        return (hits / total) * 100


class RecentlyViewedMiddleware(MiddlewareMixin):
    """
    Track recently viewed products in session.
    Stores up to 10 most recent product IDs.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Only track on product detail pages
        if view_func.__name__ == "product_detail" and "slug" in view_kwargs:
            from shop.models import Product

            try:
                product = Product.available_items.available().get(
                    slug=view_kwargs["slug"]
                )

                # Initialize recently viewed list
                if "recently_viewed" not in request.session:
                    request.session["recently_viewed"] = []

                recently_viewed = request.session["recently_viewed"]

                # Remove product if already in list
                if product.id in recently_viewed:
                    recently_viewed.remove(product.id)

                # Add to beginning of list
                recently_viewed.insert(0, product.id)

                # Keep only last 10 products
                request.session["recently_viewed"] = recently_viewed[:10]
                request.session.modified = True

            except Product.DoesNotExist:
                pass

        return None
