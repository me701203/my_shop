from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.utils.translation import gettext as _

from cart.forms import CartAddProductForm
from .models import Category, Product
from .recommender import Recommender


def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Product.objects.filter(available=True)
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)
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
    product = get_object_or_404(Product, id=id, slug=slug, available=True)

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
