from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings
from shop.models import Category, Product
from shop.views import get_cache_key_with_version


class Command(BaseCommand):
    help = "Warm up cache for popular categories and products"

    def add_arguments(self, parser):
        parser.add_argument(
            "--categories",
            type=str,
            help="Comma-separated category slugs to warm (default: all)",
        )
        parser.add_argument(
            "--top-products",
            type=int,
            default=10,
            help="Number of top products to warm (default: 10)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting cache warming..."))

        # Warm category sidebar
        self.warm_category_sidebar()

        # Warm product lists
        category_slugs = options.get("categories")
        if category_slugs:
            slugs = [s.strip() for s in category_slugs.split(",")]
            self.warm_specific_categories(slugs)
        else:
            self.warm_all_categories()

        # Warm top products
        top_count = options["top_products"]
        self.warm_top_products(top_count)

        self.stdout.write(self.style.SUCCESS("Cache warming completed!"))

    def warm_category_sidebar(self):
        """Warm category sidebar cache"""
        from shop.models import get_cache_version

        cache_key = get_cache_key_with_version("category_sidebar", "category_sidebar")
        categories = list(Category.objects.all().prefetch_related("translations"))
        timeout = settings.CACHE_TTL.get("category_sidebar", 3600)
        cache.set(cache_key, categories, timeout=timeout)

        self.stdout.write(f"  ✓ Warmed category sidebar ({len(categories)} categories)")

    def warm_all_categories(self):
        """Warm all category product lists"""
        from shop.models import get_cache_version

        # Warm "all products" list
        cache_key = get_cache_key_with_version("product_list_all", "product_list_all")
        products = list(
            Product.available_items.available()
            .with_stock_info()
            .select_related("category")
            .prefetch_related("translations")
        )
        timeout = settings.CACHE_TTL.get("product_list", 900)
        cache.set(cache_key, products, timeout=timeout)
        self.stdout.write(f"  ✓ Warmed all products list ({len(products)} products)")

        # Warm each category
        categories = Category.objects.all()
        for category in categories:
            self.warm_category(category)

    def warm_specific_categories(self, slugs):
        """Warm specific category product lists"""
        categories = Category.objects.filter(slug__in=slugs)
        for category in categories:
            self.warm_category(category)

    def warm_category(self, category):
        """Warm a single category's product list"""
        from shop.models import get_cache_version

        version_type = f"product_list_category_{category.id}"
        cache_key = get_cache_key_with_version(
            f"product_list_category_{category.slug}", version_type
        )

        products = list(
            Product.available_items.available()
            .with_stock_info()
            .filter(category=category)
            .select_related("category")
            .prefetch_related("translations")
        )

        timeout = settings.CACHE_TTL.get("product_list", 900)
        cache.set(cache_key, products, timeout=timeout)

        self.stdout.write(
            f'  ✓ Warmed category "{category.name}" ({len(products)} products)'
        )

    def warm_top_products(self, count):
        """Warm top N product detail pages"""
        from shop.models import get_cache_version
        from shop.recommender import Recommender

        # Get top products by ID (you can customize this query)
        products = Product.available_items.available()[:count]
        recommender = Recommender()

        warmed = 0
        for product in products:
            version = get_cache_version("product_detail")
            cache_key = f"product_detail:{product.id}:v{version}"

            # Get recommendations
            recommended_products = recommender.suggest_products_for([product], 4)

            cached_data = {
                "product": product,
                "recommended_products": recommended_products,
            }

            timeout = settings.CACHE_TTL.get("product_detail", 1800)
            cache.set(cache_key, cached_data, timeout=timeout)
            warmed += 1

        self.stdout.write(f"  ✓ Warmed {warmed} product detail pages")
