from django.shortcuts import redirect
from django.utils import timezone
from django.contrib import messages
from django.conf import settings

from .models import Coupon
from .forms import CouponApplyForm


def coupon_apply(request):
    now = timezone.now()
    form = CouponApplyForm(request.POST)

    if form.is_valid():
        code = form.cleaned_data["code"].strip()

        try:
            coupon = Coupon.objects.get(
                code__iexact=code,
                active=True,
                valid_from__lte=now,
                valid_to__gte=now,
            )
        except Coupon.DoesNotExist:
            messages.error(request, "Invalid or expired coupon.")
            request.session["coupon_id"] = None
            return redirect("cart:cart_detail")

        # restrictions
        if coupon.min_order_amount:
            cart_total = request.cart.get_total_price()
            if cart_total < coupon.min_order_amount:
                messages.error(request, "Order amount too low for this coupon.")
                return redirect("cart:cart_detail")

        if coupon.max_uses and coupon.uses >= coupon.max_uses:
            messages.error(request, "This coupon has reached its usage limit.")
            return redirect("cart:cart_detail")

        if coupon.users.exists() and request.user.is_authenticated:
            if request.user not in coupon.users.all():
                messages.error(request, "You are not allowed to use this coupon.")
                return redirect("cart:cart_detail")

        # all good → apply it
        request.session["coupon_id"] = coupon.id
        messages.success(request, "Coupon applied successfully.")

    return redirect("cart:cart_detail")
