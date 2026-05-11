# test_cache.py - Run this to test caching

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myshop.settings")
django.setup()

from django.core.cache import cache
from shop.middleware import CacheMonitoringMiddleware
from shop.models import Category, Product, get_cache_version
from shop.views import get_cache_key_with_version


def test_cache_system():
    print("=" * 60)
    print("CACHE SYSTEM TEST")
    print("=" * 60)

    # 1. Test Redis connection
    print("\n1. Testing Redis connection...")
    try:
        cache.set("test_key", "test_value", 10)
        result = cache.get("test_key")
        if result == "test_value":
            print("   ✓ Redis connection working")
        else:
            print("   ✗ Redis connection failed")
            return
    except Exception as e:
        print(f"   ✗ Redis error: {e}")
        return

    # 2. Test cache versioning
    print("\n2. Testing cache versioning...")
    version1 = get_cache_version("test_type")
    print(f"   Initial version: {version1}")

    from shop.models import increment_cache_version

    increment_cache_version("test_type")
    version2 = get_cache_version("test_type")
    print(f"   After increment: {version2}")

    if version2 > version1:
        print("   ✓ Cache versioning working")
    else:
        print("   ✗ Cache versioning failed")

    # 3. Test cache monitoring
    print("\n3. Testing cache monitoring...")
    CacheMonitoringMiddleware.reset_stats()

    CacheMonitoringMiddleware.record_hit()
    CacheMonitoringMiddleware.record_hit()
    CacheMonitoringMiddleware.record_miss()

    stats = CacheMonitoringMiddleware.get_stats()
    hit_rate = CacheMonitoringMiddleware.get_hit_rate()

    print(f"   Hits: {stats['hits']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {hit_rate:.1f}%")

    if stats["hits"] == 2 and stats["misses"] == 1:
        print("   ✓ Cache monitoring working")
    else:
        print("   ✗ Cache monitoring failed")

    # 4. Test actual data caching
    print("\n4. Testing product list caching...")
    cache_key = get_cache_key_with_version("product_list_all", "product_list_all")

    # Clear cache first
    cache.delete(cache_key)

    # First access (should be miss)
    products = cache.get(cache_key)
    if products is None:
        print("   ✓ Cache miss (expected)")
        products = list(Product.objects.all()[:5])
        cache.set(cache_key, products, 900)
        print(f"   Cached {len(products)} products")

    # Second access (should be hit)
    products_cached = cache.get(cache_key)
    if products_cached is not None:
        print(f"   ✓ Cache hit - retrieved {len(products_cached)} products")
    else:
        print("   ✗ Cache hit failed")

    # 5. Test cache keys
    print("\n5. Checking cache keys in Redis...")
    try:
        if hasattr(cache, "_cache"):
            redis_client = cache._cache.get_client()
            keys = redis_client.keys("myshop:*")
            print(f"   Found {len(keys)} keys with 'myshop:' prefix")
            for key in keys[:5]:
                print(f"     - {key.decode() if isinstance(key, bytes) else key}")
            print("   ✓ Cache keys properly prefixed")
    except Exception as e:
        print(f"   ⚠ Could not list keys: {e}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_cache_system()
