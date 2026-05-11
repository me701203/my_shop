from decimal import Decimal
from django.db import transaction

from django.conf import settings
from shop.models import Product, ProductVariant
from .forms import CartAddProductForm
from coupon.models import Coupon


class Cart:
    def __init__(self, request):
        """
        Initialize the cart.
        """
        self.session = request.session
        self.coupon_id = self.session.get("coupon_id")

        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            # save an empty cart in the session
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def __iter__(self):
        product_ids = []
        variant_ids = []

        # Collect IDs safely
        for key in self.cart.keys():
            parts = key.split(":")
            if len(parts) == 1:
                product_id = int(parts[0])
                variant_id = "default"
            else:
                product_id = int(parts[0])
                variant_id = parts[1]

            if product_id not in product_ids:
                product_ids.append(product_id)

            if variant_id != "default":
                vid = int(variant_id)
                if vid not in variant_ids:
                    variant_ids.append(vid)

        # Bulk fetch products
        products = Product.objects.filter(id__in=product_ids).select_related("category")
        products_map = {p.id: p for p in products}

        # Bulk fetch variants
        variants = ProductVariant.objects.filter(id__in=variant_ids).select_related(
            "product"
        )
        variants_map = {v.id: v for v in variants}

        # Yield cart items
        for key, item in self.cart.items():
            parts = key.split(":")
            if len(parts) == 1:
                product_id = int(parts[0])
                variant_id = "default"
            else:
                product_id = int(parts[0])
                variant_id = parts[1]

            product = products_map.get(product_id)
            variant = None

            if variant_id != "default":
                variant = variants_map.get(int(variant_id))

            item = item.copy()
            item["key"] = key
            item["product"] = product
            item["variant"] = variant
            item["price"] = Decimal(item["price"])
            item["total_price"] = item["price"] * item["quantity"]

            # Add stock info for easier template access
            if variant:
                item["available_stock"] = variant.stock
                item["is_variant"] = True
            else:
                item["available_stock"] = product.stock if product else 0
                item["is_variant"] = False

            # Create quantity update form
            item["update_quantity_form"] = CartAddProductForm(
                initial={
                    "quantity": item["quantity"],
                    "override": True,
                    "variant_id": variant.id if variant else None,
                }
            )

            yield item

    def __len__(self):
        """
        Count all items in the cart.
        """
        return sum(item["quantity"] for item in self.cart.values())

    def get_current_quantity(self, product_id, variant_id=None):
        """
        Get the current quantity of a specific product/variant in the cart.
        Returns 0 if not in cart.
        """
        variant_key = str(variant_id) if variant_id else "default"
        key = f"{product_id}:{variant_key}"

        if key in self.cart:
            return self.cart[key]["quantity"]
        return 0

    def add(self, product, quantity=1, override_quantity=False, variant_id=None):
        """
        Add a product (with optional variant) to the cart or update its quantity.
        Now includes proper stock validation against existing cart quantities.

        Returns tuple: (success: bool, error_message: str or None, available_stock: int)
        """
        variant_key = str(variant_id) if variant_id else "default"
        key = f"{product.id}:{variant_key}"

        # Determine available stock and price
        if variant_id:
            try:
                with transaction.atomic():
                    variant = ProductVariant.objects.select_for_update().get(
                        id=variant_id, product=product
                    )
                    available_stock = variant.stock
                    price = variant.get_price()
            except ProductVariant.DoesNotExist:
                return False, "Invalid variant selected.", 0
        else:
            # Refresh product stock from DB to get latest value
            product.refresh_from_db()
            available_stock = product.stock
            price = product.price

        # Calculate what the new quantity would be
        current_quantity = self.cart.get(key, {}).get("quantity", 0)

        if override_quantity:
            new_quantity = quantity
        else:
            new_quantity = current_quantity + quantity

        # Validate against available stock
        if new_quantity > available_stock:
            return (
                False,
                f"Not enough stock. Available: {available_stock}, requested: {new_quantity}",
                available_stock,
            )

        if new_quantity <= 0:
            return False, "Quantity must be positive.", available_stock

        # Stock validation passed - update cart
        if key not in self.cart:
            self.cart[key] = {
                "quantity": 0,
                "price": str(price),
                "variant_id": variant_id,
            }

        self.cart[key]["quantity"] = new_quantity
        self.save()

        return True, None, available_stock

    def save(self):
        # mark the session as "modified" to make sure it gets saved
        self.session.modified = True

    def remove(self, product, variant_id=None):
        variant_key = str(variant_id) if variant_id else "default"
        key = f"{product.id}:{variant_key}"
        if key in self.cart:
            del self.cart[key]
            self.save()

    def clear(self):
        # remove cart from session
        del self.session[settings.CART_SESSION_ID]
        self.save()

    def get_total_price(self):
        if hasattr(self, "_total_price"):
            return self._total_price

        self._total_price = sum(
            Decimal(item["price"]) * item["quantity"] for item in self.cart.values()
        )
        return self._total_price

    @property
    def coupon(self):
        if self.coupon_id:
            try:
                return Coupon.objects.get(id=self.coupon_id, active=True)
            except Coupon.DoesNotExist:
                pass
        return None

    def get_discount(self):
        if hasattr(self, "_discount"):
            return self._discount

        coupon = self.coupon
        if not coupon:
            self._discount = 0
            return self._discount

        total = self.get_total_price()

        if coupon.discount_type == Coupon.PERCENTAGE:
            discount = total * (coupon.discount_value / 100)
            if coupon.max_discount_amount:
                discount = min(discount, coupon.max_discount_amount)
            self._discount = discount
        else:
            if coupon.max_discount_amount:
                self._discount = min(coupon.discount_value, coupon.max_discount_amount)
            else:
                self._discount = coupon.discount_value

        return self._discount

    def get_total_price_after_discount(self):
        return self.get_total_price() - self.get_discount()

    def set_quantity(self, key, quantity):
        """
        Set exact quantity for a cart line using its key.
        If quantity <= 0, remove the item.
        """
        if key in self.cart:
            if quantity > 0:
                self.cart[key]["quantity"] = quantity
            else:
                del self.cart[key]
            self.save()

    def revalidate_stock(self):
        """
        Ensure cart quantities do not exceed real stock.
        Returns dict with adjustment details: {'changed': bool, 'adjustments': list}
        """
        changed = False
        adjustments = []

        # We must iterate over cart items using __iter__ to get real product objects
        for item in self:
            product = item["product"]
            variant = item.get("variant")
            qty = item["quantity"]

            real_stock = variant.stock if variant else product.stock

            if qty > real_stock:
                new_qty = max(real_stock, 0)
                key = item["key"]

                adjustments.append(
                    {
                        "key": key,
                        "product": product,
                        "variant": variant,
                        "old_qty": qty,
                        "new_qty": new_qty,
                    }
                )

                if new_qty > 0:
                    self.cart[key]["quantity"] = new_qty
                else:
                    del self.cart[key]

                changed = True

        if changed:
            self.save()

        return {"changed": changed, "adjustments": adjustments}

    def has_stock_issues(self):
        """
        Check if any cart item exceeds available stock.
        Returns True if there are stock problems.
        """
        for item in self:
            product = item["product"]
            variant = item.get("variant")
            quantity = item["quantity"]

            available = variant.stock if variant else product.stock

            if quantity > available:
                return True

        return False
