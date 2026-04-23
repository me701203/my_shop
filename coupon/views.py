from django.shortcuts import redirect
from django.utils import timezone
from django.contrib import messages
from django.conf import settings

from .models import Coupon
from .forms import CouponApplyForm
from cart.cart import Cart


def coupon_apply(request):
    now = timezone.now()
    form = CouponApplyForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Please enter a valid coupon code.")
        return redirect("cart:cart_detail")

    code = form.cleaned_data["code"].strip()

    # Check if coupon exists
    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        messages.error(request, "This coupon does not exist.")
        return redirect("cart:cart_detail")

    # Check active flag
    if not coupon.active:
        messages.error(request, "This coupon is not active.")
        return redirect("cart:cart_detail")

    # Check date validity
    if coupon.valid_from and coupon.valid_from > now:
        messages.error(request, "This coupon is not valid yet.")
        return redirect("cart:cart_detail")

    if coupon.valid_to and coupon.valid_to < now:
        messages.error(request, "This coupon has expired.")
        return redirect("cart:cart_detail")

    # Check usage limit
    if coupon.max_uses and coupon.uses >= coupon.max_uses:
        messages.error(request, "This coupon has reached its usage limit.")
        return redirect("cart:cart_detail")

    # User-specific coupon
    if coupon.users.exists():
        if not request.user.is_authenticated:
            messages.error(request, "You must be logged in to use this coupon.")
            return redirect("cart:cart_detail")

        if request.user not in coupon.users.all():
            messages.error(request, "You are not allowed to use this coupon.")
            return redirect("cart:cart_detail")

    # Minimum order amount
    cart = Cart(request)
    cart_total = cart.get_total_price()

    if coupon.min_order_amount and cart_total < coupon.min_order_amount:
        messages.error(
            request,
            f"Your order total must be at least {coupon.min_order_amount} to use this coupon.",
        )
        return redirect("cart:cart_detail")

    # Everything OK → Apply coupon
    request.session["coupon_id"] = coupon.id
    request.session.modified = True

    coupon.uses += 1
    coupon.save()

    messages.success(request, "Coupon applied successfully.")

    return redirect("cart:cart_detail")
