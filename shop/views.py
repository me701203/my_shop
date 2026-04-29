from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse, Http404
from django.utils.translation import gettext as _
from django.core.cache import cache

from cart.forms import CartAddProductForm
from .models import Category, Product
from .recommender import Recommender


def product_list(request, category_slug=None):
    category = None

    # Category sidebar cache
    categories = cache.get("category_sidebar")
    if categories is None:
        # print("CACHE MISS: categories") # debug Verify Category Sidebar Cache
        categories = list(Category.objects.all().prefetch_related("translations"))
        cache.set("category_sidebar", categories, timeout=None)
    # debug Verify Category Sidebar Cache
    # else:
    # print("CACHE HIT: categories")

    # Product list cache key
    if category_slug:
        cache_key = f"product_list_category_{category_slug}"
    else:
        cache_key = "product_list_all"

    products = cache.get(cache_key)

    if products is None:
        # print("CACHE MISS:", cache_key)  # debug Verify Product List Cache
        products = Product.available_items.available()  # Strong availability protection

        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)
            products = products.filter(category=category)

        products = list(products.select_related("category"))
        cache.set(cache_key, products, timeout=None)

    else:
        if category_slug:
            category = get_object_or_404(Category, slug=category_slug)

    return render(
        request,
        "shop/product/list.html",
        {
            "category": category,
            "categories": categories,
            "products": products,
        },
    )


def product_detail(request, id, slug):
    product = get_object_or_404(Product, id=id, slug=slug)

    if not product.is_in_stock():
        raise Http404(_("This product is out of stock."))

    cart_product_form = CartAddProductForm()

    recommender = Recommender()
    recommended_products = recommender.suggest_products_for([product], 4)

    return render(
        request,
        "shop/product/detail.html",
        {
            "product": product,
            "cart_product_form": cart_product_form,
            "recommended_products": recommended_products,
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
            {"status": "error", "message": _("invalid mode")}, status=400
        )

    # If form submitted normally, redirect back
    next_url = request.POST.get("next") or request.GET.get("next") or "/"
    return redirect(next_url)
