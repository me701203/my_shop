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

        # Validate variant requirement
        if product.variants.exists() and not variant_id:
            error_msg = _("Please select a variant for this product.")
            if is_ajax:
                return JsonResponse(
                    {"ok": False, "error": error_msg},
                    status=400,
                )
            messages.error(request, error_msg)
            return redirect("shop:product_detail", id=product.id, slug=product.slug)

        # Use the improved Cart.add() method which now handles all validation
        success, error_msg, available_stock = cart.add(
            product=product,
            quantity=quantity,
            override_quantity=override,
            variant_id=variant_id,
        )

        if not success:
            # Stock validation failed
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": error_msg,
                        "available_stock": available_stock,
                    },
                    status=400,
                )
            messages.error(request, error_msg)
            return redirect("shop:product_detail", id=product.id, slug=product.slug)

        # Success - return updated cart data
        if is_ajax:
            # Recompute totals from cart
            total_price = cart.get_total_price()

            # Find this line's total
            variant_key = str(variant_id) if variant_id else "default"
            key = f"{product.id}:{variant_key}"
            line = cart.cart[key]
            line_total = Decimal(line["price"]) * line["quantity"]

            discount = cart.get_discount()
            total_after_discount = cart.get_total_price_after_discount()

            return JsonResponse(
                {
                    "ok": True,
                    "message": _("Product added to cart successfully."),
                    "cart_total": str(total_price),
                    "line_total": str(line_total),
                    "line_quantity": line["quantity"],
                    "discount": str(discount),
                    "total_after_discount": str(total_after_discount),
                    "available_stock": available_stock,
                }
            )

        messages.success(request, _("Product added to cart successfully."))
        return redirect("cart:cart_detail")

    else:
        # Form validation failed
        error_msg = _("Invalid form data.")
        if form.errors:
            # Get first error message
            first_error = list(form.errors.values())[0][0]
            error_msg = first_error

        if is_ajax:
            return JsonResponse(
                {"ok": False, "error": error_msg},
                status=400,
            )
        messages.error(request, error_msg)
        return redirect("shop:product_detail", id=product.id, slug=product.slug)


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
        discount = cart.get_discount()
        total_after_discount = cart.get_total_price_after_discount()

        return JsonResponse(
            {
                "ok": True,
                "cart_total": str(total_price),
                "discount": str(discount),
                "total_after_discount": str(total_after_discount),
                "removed": existed,
            }
        )

    messages.success(request, _("Item removed from cart."))
    return redirect("cart:cart_detail")


def cart_detail(request):
    cart = Cart(request)

    # Atomically revalidate stock and get adjustment details
    revalidation_result = cart.revalidate_stock()

    stock_issue = revalidation_result["changed"]
    stock_adjustments = revalidation_result["adjustments"]

    # Show messages for adjustments
    if stock_adjustments:
        for adj in stock_adjustments:
            product_name = adj["product"].name
            if adj["variant"]:
                product_name += f" ({adj['variant'].name})"

            if adj["new_qty"] == 0:
                messages.warning(
                    request,
                    _(
                        f"{product_name} is out of stock and was removed from your cart."
                    ),
                )
            else:
                messages.warning(
                    request,
                    _(
                        f"{product_name} quantity reduced from {adj['old_qty']} to {adj['new_qty']} due to limited stock."
                    ),
                )

    return render(
        request,
        "cart/detail.html",
        {
            "cart": cart,
            "stock_issue": stock_issue,
            "stock_adjustments": stock_adjustments,
        },
    )
