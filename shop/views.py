import json
from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse, Http404
from django.utils.translation import gettext as _
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import Q, Min, Max, Avg, Count
from django.views.decorators.http import require_POST, require_http_methods
from django.db import IntegrityError
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
import logging


from cart.forms import CartAddProductForm
from .models import Category, Product, Review, StockAlert
from .recommender import Recommender
from .middleware import CacheMonitoringMiddleware
from .forms import ReviewForm
from orders.models import OrderItem
from .tasks import send_stock_alert_email

logger = logging.getLogger(__name__)


def get_cache_key_with_version(base_key, version_type):
    """Generate cache key with version"""
    from .models import get_cache_version

    version = get_cache_version(version_type)
    return f"{base_key}:v{version}"


def product_list(request, category_slug=None):
    category = None

    # Category sidebar cache with versioning
    cache_key = get_cache_key_with_version("category_sidebar", "category_sidebar")
    categories = cache.get(cache_key)

    if categories is None:
        CacheMonitoringMiddleware.record_miss()
        categories = list(Category.objects.all().prefetch_related("translations"))
        timeout = settings.CACHE_TTL.get("category_sidebar", 3600)
        cache.set(cache_key, categories, timeout=timeout)
        CacheMonitoringMiddleware.record_set()
    else:
        CacheMonitoringMiddleware.record_hit()

    # Product list cache with versioning
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        version_type = f"product_list_category_{category.id}"
        base_cache_key = f"product_list_category_{category_slug}"
    else:
        version_type = "product_list_all"
        base_cache_key = "product_list_all"

    cache_key = get_cache_key_with_version(base_cache_key, version_type)
    products = cache.get(cache_key)

    if products is None:
        CacheMonitoringMiddleware.record_miss()
        # Use available() filter + stock annotation
        products = (
            Product.objects.filter(available=True)
            .select_related("category")
            .prefetch_related("translations", "variants")
        )

        if category_slug:
            products = products.filter(category=category)

        # Convert to list for caching
        products = list(products)
        timeout = settings.CACHE_TTL.get("product_list", 900)
        cache.set(cache_key, products, timeout=timeout)
        CacheMonitoringMiddleware.record_set()
    else:
        CacheMonitoringMiddleware.record_hit()

    return render(
        request,
        "shop/product/list.html",
        {
            "category": category,
            "categories": categories,
            "products": products,
        },
    )


@ratelimit(key="user_or_ip", rate="10/h", method="POST")
def product_detail(request, id, slug):
    """Product detail view with caching and reviews"""
    from .models import get_cache_version, ProductView
    from django.db.models import F

    # Check if rate limited
    if getattr(request, "limited", False):
        logger.warning(
            f"Review rate limit exceeded: user_id={request.user.id}, "
            f"product_id={id}, ip={request.META.get('REMOTE_ADDR')}"
        )
        messages.error(
            request, _("You have submitted too many reviews. Please try again later.")
        )
        return redirect("shop:product_detail", id=id, slug=slug)

    # Generate cache key with version
    version = get_cache_version("product_detail")
    cache_key = f"product_detail:{id}:v{version}"

    # Try to get from cache
    cached_data = cache.get(cache_key)

    if cached_data is None:
        CacheMonitoringMiddleware.record_miss()
        # Fetch product
        product = get_object_or_404(
            Product.objects.prefetch_related("variants", "reviews__user"),
            id=id,
            slug=slug,
        )

        if not product.is_in_stock():
            raise Http404(_("This product is out of stock."))

        # Get recommendations
        recommender = Recommender()
        recommended_products = recommender.suggest_products_for([product], 4)

        # Cache the data
        cached_data = {
            "product": product,
            "recommended_products": recommended_products,
        }
        timeout = settings.CACHE_TTL.get("product_detail", 1800)
        cache.set(cache_key, cached_data, timeout=timeout)
        CacheMonitoringMiddleware.record_set()
    else:
        CacheMonitoringMiddleware.record_hit()
        product = cached_data["product"]
        recommended_products = cached_data["recommended_products"]

    # Track product view (outside cache - always track)
    ProductView.objects.create(
        product=product,
        user=request.user if request.user.is_authenticated else None,
        session_key=request.session.session_key or "",
        ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
    )

    # Increment view count
    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)

    # Reviews (not cached - need fresh data)
    reviews = product.reviews.select_related("user").all()
    user_review = None
    review_form = None

    if request.user.is_authenticated:
        user_review = reviews.filter(user=request.user).first()

        if request.method == "POST" and "submit_review" in request.POST:
            if user_review:
                review_form = ReviewForm(request.POST, instance=user_review)
            else:
                review_form = ReviewForm(request.POST)

            if review_form.is_valid():
                review = review_form.save(commit=False)
                review.product = product
                review.user = request.user

                # Check if user has purchased this product
                has_purchased = OrderItem.objects.filter(
                    order__user=request.user,
                    product=product,
                    order__payment_status="paid",
                ).exists()

                review.is_verified_purchase = has_purchased
                review.save()

                messages.success(
                    request, _("Your review has been submitted successfully!")
                )
                return redirect("shop:product_detail", id=product.id, slug=product.slug)
        else:
            if user_review:
                review_form = ReviewForm(instance=user_review)
            else:
                review_form = ReviewForm()

    # Calculate average rating
    from django.db.models import Avg

    avg_rating = reviews.aggregate(Avg("rating"))["rating__avg"]

    cart_product_form = CartAddProductForm()

    return render(
        request,
        "shop/product/detail.html",
        {
            "product": product,
            "cart_product_form": cart_product_form,
            "recommended_products": recommended_products,
            "reviews": reviews,
            "user_review": user_review,
            "review_form": review_form,
            "avg_rating": avg_rating,
            "review_count": reviews.count(),
        },
    )


def set_digits(request):
    # Support both GET and POST
    mode = request.POST.get("digits") or request.GET.get("mode")

    # Normalize input
    if mode == "fa":
        request.session["digits"] = "fa"
    elif mode == "en":
        request.session["digits"] = "en"
    else:
        return JsonResponse(
            {"status": "error", "message": str(_("invalid mode"))}, status=400
        )

    # If form submitted normally, redirect back
    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    return redirect(next_url)


def product_search(request):
    """Full-text search view with ranking"""
    query = request.GET.get("q", "").strip()
    results = []
    sort_by = request.GET.get("sort", "relevance")

    if query:
        # Create search query
        search_query = SearchQuery(query, config="english")

        # Search in name and description with ranking
        results = (
            Product.available_items.available()
            .annotate(rank=SearchRank("search_vector", search_query))
            .filter(search_vector=search_query)
            .select_related("category")
            .prefetch_related("translations", "variants")
        )

        # Fallback: if no results, try case-insensitive LIKE search
        if not results.exists():
            results = (
                Product.available_items.available()
                .filter(
                    Q(translations__name__icontains=query)
                    | Q(translations__description__icontains=query)
                )
                .distinct()
                .select_related("category")
                .prefetch_related("translations", "variants")
            )

        # Apply sorting
        if sort_by == "price_low":
            results = results.order_by("price")
        elif sort_by == "price_high":
            results = results.order_by("-price")
        elif sort_by == "newest":
            results = results.order_by("-created")
        elif sort_by == "rating":
            from django.db.models import Avg

            results = results.annotate(avg_rating=Avg("reviews__rating")).order_by(
                "-avg_rating"
            )
        else:  # relevance (default)
            results = results.order_by("-rank")

    return render(
        request,
        "shop/product/search.html",
        {
            "query": query,
            "results": results,
            "result_count": results.count() if results else 0,
            "sort_by": sort_by,
        },
    )


from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse


@staff_member_required
def cache_stats(request):
    """View cache statistics (staff only)"""
    from .middleware import CacheMonitoringMiddleware

    stats = CacheMonitoringMiddleware.get_stats()
    hit_rate = CacheMonitoringMiddleware.get_hit_rate()

    # Get Redis info if available
    redis_info = {}
    try:
        from django.core.cache import cache

        if hasattr(cache, "_cache"):
            redis_client = cache._cache.get_client()
            info = redis_client.info("stats")
            redis_info = {
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands": info.get("total_commands_processed", 0),
            }
    except Exception as e:
        redis_info = {"error": str(e)}

    return JsonResponse(
        {
            "application_stats": {
                "hits": stats.get("hits", 0),
                "misses": stats.get("misses", 0),
                "sets": stats.get("sets", 0),
                "hit_rate": f"{hit_rate:.2f}%",
            },
            "redis_stats": redis_info,
        }
    )


@login_required
def wishlist_view(request):
    """Display user's wishlist"""
    from .models import Wishlist

    wishlist_items = (
        Wishlist.objects.filter(user=request.user)
        .select_related("product__category")
        .prefetch_related("product__translations", "product__variants")
    )

    return render(
        request,
        "shop/wishlist.html",
        {
            "wishlist_items": wishlist_items,
            "wishlist_count": wishlist_items.count(),
        },
    )


@login_required
@require_POST
@ratelimit(key="user", rate="30/m", method="POST")
def wishlist_add(request, product_id):
    """Add product to wishlist (AJAX endpoint)"""
    from .models import Wishlist

    # Check if rate limited
    if getattr(request, "limited", False):
        logger.warning(
            f"Wishlist operation rate limit: user_id={request.user.id}, "
            f"product_id={product_id}, operation='add/remove/toggle', "
            f"ip={request.META.get('REMOTE_ADDR')}"
        )
        messages.error(request, _("Operation too fast. Please wait a moment."))
        return redirect("shop:product_list")

    try:
        product = get_object_or_404(Product, id=product_id)

        # Try to create wishlist item
        wishlist_item, created = Wishlist.objects.get_or_create(
            user=request.user, product=product
        )

        if created:
            message = _("Product added to wishlist")
            status = "added"
        else:
            message = _("Product already in wishlist")
            status = "exists"

        # Get updated wishlist count
        wishlist_count = Wishlist.objects.filter(user=request.user).count()

        return JsonResponse(
            {
                "ok": True,
                "status": status,
                "message": str(message),
                "wishlist_count": wishlist_count,
            }
        )

    except Exception as e:
        return JsonResponse(
            {
                "ok": False,
                "error": str(e),
            },
            status=400,
        )


@login_required
@require_POST
@ratelimit(key="user", rate="30/m", method="POST")
def wishlist_remove(request, product_id):
    """Remove product from wishlist (AJAX endpoint)"""
    from .models import Wishlist
    from django.utils.translation import gettext_lazy as _

    # Check if rate limited
    if getattr(request, "limited", False):
        logger.warning(
            f"Wishlist operation rate limit: user_id={request.user.id}, "
            f"product_id={product_id}, operation='add/remove/toggle', "
            f"ip={request.META.get('REMOTE_ADDR')}"
        )
        messages.error(request, _("Operation too fast. Please wait a moment."))
        return redirect("shop:wishlist")

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse(
            {
                "ok": False,
                "error": "Product not found",
            },
            status=404,
        )

    try:
        wishlist_items = Wishlist.objects.filter(user=request.user, product=product)
        deleted_count, _ = Wishlist.objects.filter(
            user=request.user, product=product
        ).delete()

        if deleted_count > 0:
            message = "Product removed from wishlist"
            status = "removed"
        else:
            message = "Product not in wishlist"
            status = "not_found"

        # Get updated wishlist count
        wishlist_count = Wishlist.objects.filter(user=request.user).count()

        response_data = {
            "ok": True,
            "status": status,
            "message": message,
            "wishlist_count": wishlist_count,
        }

        return JsonResponse(response_data)

    except Exception as e:
        import traceback

        traceback.print_exc()

        return JsonResponse(
            {
                "ok": False,
                "error": str(e),
            },
            status=400,
        )


@login_required
@require_POST
@ratelimit(key="user", rate="30/m", method="POST")
def wishlist_toggle(request, product_id):
    """Toggle product in wishlist - works with both GET and POST"""
    from .models import Wishlist

    # Check if rate limited
    if getattr(request, "limited", False):
        logger.warning(
            f"Wishlist operation rate limit: user_id={request.user.id}, "
            f"product_id={product_id}, operation='add/remove/toggle', "
            f"ip={request.META.get('REMOTE_ADDR')}"
        )
        messages.error(request, _("Operation too fast. Please wait a moment."))
        return redirect("shop:product_list")

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(_("Product not found")),
                },
                status=404,
            )
        messages.error(request, str(_("Product not found")))
        return redirect("shop:product_list")

    try:
        wishlist_item = Wishlist.objects.filter(
            user=request.user, product=product
        ).first()

        if wishlist_item:
            # Remove from wishlist
            wishlist_item.delete()
            message = _("Product removed from wishlist")
            status = "removed"
            in_wishlist = False
        else:
            # Add to wishlist
            Wishlist.objects.create(user=request.user, product=product)
            message = _("Product added to wishlist")
            status = "added"
            in_wishlist = True

        # Get updated wishlist count
        wishlist_count = Wishlist.objects.filter(user=request.user).count()

        # AJAX request
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "status": status,
                    "message": str(message),
                    "in_wishlist": in_wishlist,
                    "wishlist_count": wishlist_count,
                }
            )

        # Regular request - redirect back
        messages.success(request, message)
        return redirect(request.META.get("HTTP_REFERER", "shop:product_list"))

    except Exception as e:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(e),
                },
                status=400,
            )

        messages.error(request, str(e))
        return redirect("shop:product_list")


def advanced_search(request):
    """
    Advanced search with filters: price range, category, rating, availability.
    """
    query = request.GET.get("q", "")
    category_id = request.GET.get("category")
    min_price = request.GET.get("min_price")
    max_price = request.GET.get("max_price")
    min_rating = request.GET.get("min_rating")
    in_stock = request.GET.get("in_stock")
    sort_by = request.GET.get("sort", "relevance")

    # Base queryset
    products = (
        Product.available_items.available()
        .select_related("category")
        .prefetch_related("images")
    )

    # Text search
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        )

    # Category filter
    if category_id:
        products = products.filter(category_id=category_id)

    # Price range filter
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)

    # Rating filter
    if min_rating:
        products = products.annotate(avg_rating=Avg("reviews__rating")).filter(
            avg_rating__gte=min_rating
        )

    # Stock filter
    if in_stock == "true":
        products = products.filter(inventory__gt=0)

    # Sorting
    if sort_by == "price_low":
        products = products.order_by("price")
    elif sort_by == "price_high":
        products = products.order_by("-price")
    elif sort_by == "rating":
        products = products.annotate(avg_rating=Avg("reviews__rating")).order_by(
            "-avg_rating"
        )
    elif sort_by == "newest":
        products = products.order_by("-created")
    elif sort_by == "popular":
        products = products.order_by("-view_count", "-purchase_count")

    # Get filter options for sidebar
    categories = Category.objects.annotate(product_count=Count("products")).filter(
        product_count__gt=0
    )
    price_range = Product.available_items.available().aggregate(
        min_price=Min("price"), max_price=Max("price")
    )

    # Pagination
    paginator = Paginator(products, 12)
    page = request.GET.get("page", 1)

    try:
        products_page = paginator.page(page)
    except PageNotAnInteger:
        products_page = paginator.page(1)
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)

    context = {
        "products": products_page,
        "query": query,
        "categories": categories,
        "price_range": price_range,
        "selected_category": category_id,
        "selected_min_price": min_price,
        "selected_max_price": max_price,
        "selected_min_rating": min_rating,
        "selected_in_stock": in_stock,
        "sort_by": sort_by,
    }

    return render(request, "shop/product/search_advanced.html", context)


def search_autocomplete(request):
    """
    AJAX endpoint for search autocomplete.
    """
    query = request.GET.get("q", "")

    if len(query) < 2:
        return JsonResponse({"suggestions": []})

    products = Product.available_items.available().filter(
        Q(name__icontains=query) | Q(description__icontains=query)
    )[:10]

    suggestions = [
        {
            "id": p.id,
            "name": p.name,
            "price": str(p.price),
            "image": p.images.first().image.url if p.images.exists() else None,
            "url": p.get_absolute_url(),
        }
        for p in products
    ]

    return JsonResponse({"suggestions": suggestions})


def add_to_comparison(request, product_id):
    """
    Add product to comparison list (stored in session).
    """
    comparison_list = request.session.get("comparison", [])

    if product_id not in comparison_list:
        if len(comparison_list) >= 4:  # Max 4 products
            return JsonResponse(
                {
                    "success": False,
                    "message": str(_("You can compare up to 4 products only.")),
                }
            )

        comparison_list.append(product_id)
        request.session["comparison"] = comparison_list
        request.session.modified = True

        return JsonResponse(
            {
                "success": True,
                "count": len(comparison_list),
                "message": str(_("Product added to comparison.")),
            }
        )

    return JsonResponse(
        {"success": False, "message": str(_("Product already in comparison list."))}
    )


def remove_from_comparison(request, product_id):
    """
    Remove product from comparison list.
    """
    comparison_list = request.session.get("comparison", [])

    if product_id in comparison_list:
        comparison_list.remove(product_id)
        request.session["comparison"] = comparison_list
        request.session.modified = True

    return JsonResponse({"success": True, "count": len(comparison_list)})


def compare_products(request):
    """
    Display product comparison page.
    """
    comparison_list = request.session.get("comparison", [])

    products = (
        Product.available_items.available()
        .filter(id__in=comparison_list)
        .select_related("category")
        .prefetch_related("images", "variants")
    )

    # Maintain order from session
    products_dict = {p.id: p for p in products}
    ordered_products = [
        products_dict[pid] for pid in comparison_list if pid in products_dict
    ]

    # Get all unique attributes for comparison
    all_attributes = set()
    for product in ordered_products:
        for variant in product.variants.all():
            all_attributes.update(variant.attributes.keys())

    context = {
        "products": ordered_products,
        "all_attributes": sorted(all_attributes),
    }

    return render(request, "shop/product/compare.html", context)


def clear_comparison(request):
    """
    Clear all products from comparison.
    """
    request.session["comparison"] = []
    request.session.modified = True

    return JsonResponse({"success": True})


from .models import StockAlert


@ratelimit(key="user", rate="10/h", method="POST")
def subscribe_stock_alert(request, product_id):
    """
    Subscribe to stock alerts for out-of-stock products.
    """
    # Check if rate limited
    if getattr(request, "limited", False):
        logger.warning(
            f"Stock alert rate limit: user_id={request.user.id}, "
            f"product_id={product_id}, ip={request.META.get('REMOTE_ADDR')}"
        )
        messages.error(request, _("You have sent too many requests."))
        return redirect("shop:product_list")

    if not request.user.is_authenticated:
        return JsonResponse(
            {
                "success": False,
                "message": str(_("Please login to subscribe to stock alerts.")),
            }
        )

    try:
        product = Product.objects.get(id=product_id)

        if product.stock > 0:
            return JsonResponse(
                {
                    "success": False,
                    "message": str(_("This product is currently in stock.")),
                }
            )

        alert, created = StockAlert.objects.get_or_create(
            user=request.user, product=product, defaults={"email": request.user.email}
        )

        if created:
            return JsonResponse(
                {
                    "success": True,
                    "message": str(
                        _("You will be notified when this product is back in stock.")
                    ),
                }
            )
        else:
            return JsonResponse(
                {
                    "success": False,
                    "message": str(
                        _("You are already subscribed to alerts for this product.")
                    ),
                }
            )

    except Product.DoesNotExist:
        return JsonResponse({"success": False, "message": str(_("Product not found."))})


# Add signal to notify users when stock is updated
from django.db.models.signals import post_save
from django.dispatch import receiver


@login_required
def stock_alerts_view(request):
    """
    Display user's active stock alerts with product details.
    """
    user_email = request.user.email

    # Get all active (not yet notified) stock alerts for this user
    alerts = (
        StockAlert.objects.filter(email=user_email, notified=False)
        .select_related("product")
        .order_by("-created_at")
    )

    # Prepare alert data with product info
    alert_data = []
    for alert in alerts:
        product = alert.product
        alert_data.append(
            {
                "id": alert.id,
                "product": product,
                "created_at": alert.created_at,
                "is_available": product.total_stock > 0,
            }
        )

    context = {
        "alerts": alert_data,
        "total_alerts": len(alert_data),
    }

    return render(request, "shop/stock_alerts.html", context)


@login_required
@require_http_methods(["POST"])
def delete_stock_alert(request, alert_id):
    """
    Delete a stock alert subscription.
    """
    try:
        alert = StockAlert.objects.get(id=alert_id, email=request.user.email)
        alert.delete()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": True, "message": _("Stock alert removed successfully")}
            )
        else:
            messages.success(request, _("Stock alert removed successfully"))
            return redirect("shop:stock_alerts")

    except StockAlert.DoesNotExist:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": _("Stock alert not found")}, status=404
            )
        else:
            messages.error(request, _("Stock alert not found"))
            return redirect("shop:stock_alerts")


@receiver(post_save, sender=Product)
def check_stock_alerts(sender, instance, **kwargs):
    """
    When a product is saved, check if it's back in stock and send alerts.
    """
    if instance.stock > 0:
        # Get all unnotified alerts for this product
        alerts = StockAlert.objects.filter(product=instance, notified=False)

        for alert in alerts:
            send_stock_alert_email.delay(alert.id)


def ratelimited_error(request, exception):
    return render(request, "429.html", status=429)
