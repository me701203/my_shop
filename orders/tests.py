from decimal import Decimal
from django.test import TestCase
from django.urls import reverse

from shop.models import Product, Category
from orders.models import Order, OrderItem


class OrderCheckoutTests(TestCase):

    def setUp(self):
        self.category = Category.objects.create(slug="checkout-cat")
        self.category.set_current_language("en")
        self.category.name = "Checkout Category"
        self.category.save()

        self.product = Product.objects.create(
            category=self.category,
            slug="checkout-product",
            name="Checkout Product",
            price=Decimal("50.00"),
            stock=5,
        )

    def add_to_cart(self, quantity=2):
        session = self.client.session
        cart = {
            f"{self.product.id}:default": {
                "quantity": quantity,
                "price": "50.00",
                "variant_id": None,
            }
        }
        session["cart"] = cart
        session.save()

    def checkout(self):
        url = reverse("orders:order_create")
        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@test.com",
            "address": "Street 1",
            "postal_code": "12345",
            "city": "City",
            "gateway": "fake",
        }

        return self.client.post(url, data)

    def test_order_created_and_stock_reduced(self):
        self.add_to_cart(quantity=2)
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.items.count(), 1)
        item = order.items.first()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.product, self.product)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_checkout_fails_when_stock_insufficient(self):
        self.add_to_cart(quantity=10)
        response = self.checkout()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
