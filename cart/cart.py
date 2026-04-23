from decimal import Decimal

from django.conf import settings
from shop.models import Product
from .forms import CartAddProductForm
from coupon.models import Coupon


class Cart:
    def __init__(self, request):
        """
        Initialize the cart.
        """
        self.session = request.session
        self.coupon_id = self.session.get("coupon_id")

        print("CART INIT coupon_id:", self.coupon_id)  # for debug

        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            # save an empty cart in the session
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def __iter__(self):
        """
        Iterate over the items in the cart and get the products
        from the database.
        """
        product_ids = self.cart.keys()
        # get the product objects and add them to the cart
        products = Product.objects.filter(id__in=product_ids)

        # Create a dictionary to easily map product IDs to product objects
        product_dict = {str(p.id): p for p in products}

        for item_id, item_data in self.cart.items():
            product = product_dict.get(item_id)
            if product:  # Ensure product exists
                # Create a copy of the item data from the session
                item = item_data.copy()
                # Add the actual product object to this *temporary* item dict
                item["product"] = product
                item["price"] = Decimal(item["price"])
                item["total_price"] = item["price"] * item["quantity"]
                item["update_quantity_form"] = CartAddProductForm(
                    initial={"quantity": item["quantity"], "override": True}
                )
                yield item

    def __len__(self):
        """
        Count all items in the cart.
        """
        return sum(item["quantity"] for item in self.cart.values())

    def add(self, product, quantity=1, override_quantity=False):
        """
        Add a product to the cart or update its quantity.
        """
        product_id = str(product.id)
        if product_id not in self.cart:
            self.cart[product_id] = {
                "quantity": 0,
                "price": str(product.price),
            }
        if override_quantity:
            self.cart[product_id]["quantity"] = quantity
        else:
            self.cart[product_id]["quantity"] += quantity
        self.save()

    def save(self):
        # mark the session as "modified" to make sure it gets saved
        self.session.modified = True

    def remove(self, product):
        """
        Remove a product from the cart.
        """
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    def clear(self):
        # remove cart from session
        del self.session[settings.CART_SESSION_ID]
        self.save()

    def get_total_price(self):
        return sum(
            Decimal(item["price"]) * item["quantity"] for item in self.cart.values()
        )

    @property
    def coupon(self):
        if self.coupon_id:
            try:
                return Coupon.objects.get(id=self.coupon_id, active=True)
            except Coupon.DoesNotExist:
                pass
        return None

    def get_discount(self):
        coupon = self.coupon
        if not coupon:
            return 0

        total = self.get_total_price()

        if coupon.discount_type == Coupon.PERCENTAGE:
            discount = total * (coupon.discount_value / 100)
            if coupon.max_discount_amount:
                discount = min(discount, coupon.max_discount_amount)
            return discount

        else:  # FIXED
            if coupon.max_discount_amount:
                return min(coupon.discount_value, coupon.max_discount_amount)
            return coupon.discount_value

    def get_total_price_after_discount(self):
        return self.get_total_price() - self.get_discount()
