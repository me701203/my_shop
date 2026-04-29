from decimal import Decimal
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.conf import settings

from shop.models import Product, Category
from cart.cart import Cart
from coupon.models import Coupon


class CartTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        # Create category (REQUIRED by Product)
        self.category = Category.objects.create(slug="test-cat")
        self.category.set_current_language("en")
        self.category.name = "Test Category"
        self.category.save()

        # Create product
        self.product = Product.objects.create(
            category=self.category,
            slug="test-product",
            name="Test Product",
            price=Decimal("100.00"),
            stock=10,
        )

        # Create coupon
        self.coupon = Coupon.objects.create(
            code="TEST10",
            discount_type=Coupon.PERCENTAGE,
            discount_value=Decimal("10"),
            active=True,
        )

    def get_request(self):
        request = self.factory.get("/")
        request.session = self.client.session
        return request

    def test_cart_add_and_total(self):
        request = self.get_request()
        cart = Cart(request)
        cart.add(self.product, quantity=2)
        self.assertEqual(len(cart), 2)
        self.assertEqual(cart.get_total_price(), Decimal("200.00"))

    def test_cart_remove(self):
        request = self.get_request()
        cart = Cart(request)
        cart.add(self.product, quantity=2)
        cart.remove(self.product)
        self.assertEqual(len(cart), 0)

    def test_coupon_discount(self):
        request = self.get_request()
        request.session["coupon_id"] = self.coupon.id
        request.session.save()
        cart = Cart(request)
        cart.add(self.product, quantity=2)
        total = cart.get_total_price()
        discount = cart.get_discount()
        self.assertEqual(total, Decimal("200.00"))
        self.assertEqual(discount, Decimal("20.00"))

    def test_total_after_discount(self):
        request = self.get_request()
        request.session["coupon_id"] = self.coupon.id
        request.session.save()
        cart = Cart(request)
        cart.add(self.product, quantity=2)
        total_after = cart.get_total_price_after_discount()
        self.assertEqual(total_after, Decimal("180.00"))

    def test_revalidate_stock(self):
        request = self.get_request()
        cart = Cart(request)
        cart.add(self.product, quantity=15)
        changed = cart.revalidate_stock()
        self.assertTrue(changed)
        items = list(cart)
        self.assertEqual(items[0]["quantity"], 10)
