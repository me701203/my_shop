from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from django.utils.translation import gettext as _
from decimal import Decimal

from shop.models import Product, ProductVariant
from .cart import Cart
from .forms import CartAddProductForm


@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    form = CartAddProductForm(request.POST)

    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    if form.is_valid():
        cd = form.cleaned_data
        variant_id = cd.get("variant_id")
        quantity = cd["quantity"]
        override = cd["override"]

        # Variant-aware STOCK CHECK
        if variant_id:
            try:
                variant = ProductVariant.objects.get(id=variant_id, product=product)
            except ProductVariant.DoesNotExist:
                if is_ajax:
                    return JsonResponse(
                        {"ok": False, "error": "Invalid variant selected."},
                        status=400,
                    )
                messages.error(request, _("Invalid variant selected."))
                return redirect("cart:cart_detail")

            if not variant.is_in_stock() or quantity > variant.stock:
                if is_ajax:
                    return JsonResponse(
                        {"ok": False, "error": _("Not enough stock for this variant.")},
                        status=400,
                    )
                messages.error(
                    request, _("Not enough stock available for this variant.")
                )
                return redirect("cart:cart_detail")

        else:
            # Product WITHOUT variants
            if not product.is_in_stock() or quantity > product.stock:
                if is_ajax:
                    return JsonResponse(
                        {"ok": False, "error": "Not enough stock available."},
                        status=400,
                    )
                messages.error(request, _("Not enough stock available."))
                return redirect("cart:cart_detail")

        # If stock OK → add/update cart
        cart.add(
            product=product,
            quantity=quantity,
            override_quantity=override,
            variant_id=variant_id,
        )

        if is_ajax:
            # Recompute totals from cart
            total_price = cart.get_total_price()
            # Also find this line's total (optional but useful)
            # The key we are updating
            variant_key = str(variant_id) if variant_id else "default"
            key = f"{product.id}:{variant_key}"
            line = cart.cart[key]
            line_total = Decimal(line["price"]) * line["quantity"]

            discount = cart.get_discount()
            total_after_discount = cart.get_total_price_after_discount()

            return JsonResponse(
                {
                    "ok": True,
                    "cart_total": str(total_price),
                    "line_total": str(line_total),
                    "line_quantity": line["quantity"],
                    "discount": str(discount),
                    "total_after_discount": str(total_after_discount),
                }
            )

    # fallback: normal behavior
    return redirect("cart:cart_detail")


@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    variant_id = request.POST.get("variant_id")  # may be None

    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    # Identify key before removing (to check if it existed)
    variant_key = str(variant_id) if variant_id else "default"
    key = f"{product.id}:{variant_key}"
    existed = key in cart.cart

    cart.remove(product, variant_id=variant_id)

    if is_ajax:
        total_price = cart.get_total_price()
        return JsonResponse(
            {
                "ok": True,
                "cart_total": str(total_price),
                "removed": existed,
            }
        )

    return redirect("cart:cart_detail")


def cart_detail(request):
    cart = Cart(request)
    stock_issue = False
    stock_adjustments = []

    for item in cart:
        product = item["product"]
        quantity = item["quantity"]
        variant = item.get("variant")

        # Check stock depending on variant vs no variant
        if variant:
            available = variant.stock
        else:
            available = product.stock

        # If quantity exceeds available stock:
        if available < quantity:
            stock_issue = True

            # auto-adjust (but do NOT save to session yet)
            stock_adjustments.append(
                {
                    "key": item["key"],  # unique cart line key
                    "old_qty": quantity,
                    "new_qty": available,
                    "product": product,
                    "variant": variant,
                }
            )
    # Auto-apply quantity reductions in the session
    for adj in stock_adjustments:
        cart.set_quantity(adj["key"], adj["new_qty"])

    return render(
        request,
        "cart/detail.html",
        {
            "cart": cart,
            "stock_issue": stock_issue,
            "stock_adjustments": stock_adjustments,
        },
    )
