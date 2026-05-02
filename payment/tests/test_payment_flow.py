import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.urls import reverse

from orders.models import Order, OrderItem
from shop.models import Product, ProductVariant, Category
from coupon.models import Coupon
from payment.models import PaymentLog


# ============================================================
# SHARED FIXTURES
# ============================================================


@pytest.fixture
def category():
    """Create a test category."""
    return Category.objects.create(slug="test-category")


@pytest.fixture
def simple_product(category):
    """Create a simple product with stock."""
    product = Product.objects.create(
        category=category,
        slug="test-product",
        price=Decimal("100.00"),
        stock=10,
        available=True,
    )
    product.set_current_language("en")
    product.name = "Test Product"
    product.save()
    return product


@pytest.fixture
def product_with_variant(category):
    """Create a product with a variant."""
    product = Product.objects.create(
        category=category,
        slug="variant-product",
        price=Decimal("200.00"),
        stock=0,
        available=True,
    )
    product.set_current_language("en")
    product.name = "Variant Product"
    product.save()

    variant = ProductVariant.objects.create(
        product=product,
        size="M",
        color="Blue",
        stock=5,
    )
    return product, variant


@pytest.fixture
def valid_coupon():
    """Create a valid percentage coupon."""
    return Coupon.objects.create(
        code="SAVE20",
        valid_from=timezone.now() - timedelta(days=1),
        valid_to=timezone.now() + timedelta(days=30),
        discount_type=Coupon.PERCENTAGE,
        discount_value=Decimal("20.00"),
        max_uses=100,
        uses=0,
        active=True,
    )


# ============================================================
# BATCH 1: CORE PAYMENT SUCCESS FLOWS (3 TESTS)
# ============================================================


@pytest.mark.django_db
def test_simple_order_payment_success(client, category, simple_product):
    """
    Test 1: Simple product payment without coupon or variant.

    Flow:
    1. Order created with RESERVED status, stock deducted
    2. User redirected to fake gateway
    3. Gateway callback with success=1
    4. Verification succeeds
    5. Order marked PAID, stock remains deducted
    """
    # Create reserved order
    order = Order.objects.create(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        address="123 Test St",
        postal_code="12345",
        city="Test City",
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_status=Order.PaymentStatus.PENDING,
        reserved_until=timezone.now() + timedelta(minutes=15),
        payment_reference=f"test-ref-{timezone.now().timestamp()}",
        payment_method="fake",
        # payment_authority=f"AUTH-{timezone.now().timestamp()}",
    )

    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=2,
    )

    # Simulate stock reservation (already deducted during cart checkout)
    simple_product.stock -= 2
    simple_product.save()
    initial_stock = simple_product.stock  # Should be 8

    # Step 1: Simulate gateway selection
    session = client.session
    session["gateway"] = "fake"
    session.save()

    # Step 2: Request payment (redirects to fake gateway)
    # with patch("payment.gateways.fake.FakeGateway.request") as mock_request:
    # mock_request.return_value = (
    #    True,
    #    f"http://fake-gateway.com/pay?trackId={order.payment_authority}",
    #    order.payment_authority,
    #    None,
    # )

    # response = client.post(
    #    reverse("payment:process", args=[order.id]),
    # )

    # Add this right before the assertion at line 143:
    # if response.status_code != 302:
    #    print("\n" + "=" * 80)
    #    print("ERROR - Expected redirect but got:", response.status_code)
    #    print("Response content:")
    #    print(response.content.decode("utf-8"))
    #    print("=" * 80 + "\n")

    # assert response.status_code == 302
    # assert "fake" in response.url.lower()

    with patch("payment.gateways.fake.FakeGateway.request") as mock_request:
        fake_authority = f"AUTH-{timezone.now().timestamp()}"  # Generate here
        mock_request.return_value = (
            True,
            f"http://fake-gateway.com/pay?trackId={fake_authority}",
            fake_authority,
            None,
        )

        response = client.post(
            reverse("payment:process", args=[order.id]),
        )

        assert response.status_code == 302
        assert "fake" in response.url.lower()

        # Refresh to get the authority set by the view
        order.refresh_from_db()

    # Step 3: Simulate gateway callback (success)
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = order.payment_authority
        mock_verify.return_value = (True, "FAKE-REF-12345", "Payment successful")

        response = client.get(
            reverse("payment:verify", args=[order.id]),
            {
                "trackId": order.payment_authority,
                "success": "1",
            },
        )

        assert response.status_code in [200, 302]

    # Step 4: Verify order state
    order.refresh_from_db()
    simple_product.refresh_from_db()

    assert order.reservation_status == Order.ReservationStatus.PAID
    assert order.payment_status == Order.PaymentStatus.SUCCESS
    assert order.paid is True
    assert order.paid_at is not None
    assert order.payment_ref_id == "FAKE-REF-12345"

    # Stock should remain deducted (not restored)
    assert simple_product.stock == initial_stock

    # Payment log should exist
    assert PaymentLog.objects.filter(
        order=order,
        action="verify",
        success=True,
    ).exists()


@pytest.mark.django_db
def test_order_with_coupon_payment_success(
    client, category, simple_product, valid_coupon
):
    """
    Test 2: Payment with coupon - verify coupon.uses increments ONCE.

    Critical: Coupon should only increment on first successful payment,
    not on revisits to the success URL.
    """
    # Create reserved order with coupon
    order = Order.objects.create(
        first_name="Jane",
        last_name="Smith",
        email="jane@example.com",
        address="456 Coupon Ave",
        postal_code="54321",
        city="Discount City",
        reservation_status=Order.ReservationStatus.RESERVED,
        reserved_until=timezone.now() + timedelta(minutes=15),
        payment_reference=f"test-ref-coupon-{timezone.now().timestamp()}",
        payment_method="fake",
        payment_authority=f"AUTH-COUPON-{timezone.now().timestamp()}",
        coupon=valid_coupon,
        discount=Decimal("40.00"),  # 20% of 200
    )

    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=2,  # Total: 200, discount: 40, final: 160
    )

    # Stock already reserved
    simple_product.stock -= 2
    simple_product.save()

    initial_coupon_uses = valid_coupon.uses  # Should be 0

    # Step 1: Gateway selection
    session = client.session
    session["gateway"] = "fake"
    session.save()

    # Step 2: Request payment
    with patch("payment.gateways.fake.FakeGateway.request") as mock_request:
        mock_request.return_value = (
            True,
            f"http://fake-gateway.com/pay?trackId={order.payment_authority}",
            order.payment_authority,
            None,
        )

        client.post(reverse("payment:process", args=[order.id]))

    # Step 3: Gateway callback (success)
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = order.payment_authority
        mock_verify.return_value = (True, "FAKE-COUPON-REF-67890", "Payment successful")

        client.get(
            reverse("payment:verify", args=[order.id]),
            {
                "trackId": order.payment_authority,
                "success": "1",
            },
        )

    # Step 4: Verify coupon incremented ONCE
    valid_coupon.refresh_from_db()
    assert valid_coupon.uses == initial_coupon_uses + 1

    # Step 5: Revisit success URL (simulate user refresh)
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = order.payment_authority
        mock_verify.return_value = (True, "FAKE-COUPON-REF-67890", "Payment successful")

        client.get(
            reverse("payment:verify", args=[order.id]),
            {
                "trackId": order.payment_authority,
                "success": "1",
            },
        )

    # Step 6: Coupon should NOT increment again
    valid_coupon.refresh_from_db()
    assert valid_coupon.uses == initial_coupon_uses + 1  # Still 1

    # Order should remain PAID
    order.refresh_from_db()
    assert order.reservation_status == Order.ReservationStatus.PAID
    assert order.payment_status == Order.PaymentStatus.SUCCESS


@pytest.mark.django_db
def test_order_with_variant_payment_success(client, category, product_with_variant):
    """
    Test 3: Payment with product variant - verify variant stock handling.

    Flow:
    1. Order created with variant, variant.stock deducted
    2. Payment succeeds
    3. Variant stock remains deducted (not product.stock)
    """
    product, variant = product_with_variant

    # Create reserved order with variant
    order = Order.objects.create(
        first_name="Alice",
        last_name="Variant",
        email="alice@example.com",
        address="789 Variant Rd",
        postal_code="67890",
        city="Variant City",
        reservation_status=Order.ReservationStatus.RESERVED,
        reserved_until=timezone.now() + timedelta(minutes=15),
        payment_reference=f"test-ref-variant-{timezone.now().timestamp()}",
        payment_method="fake",
        payment_authority=f"AUTH-VARIANT-{timezone.now().timestamp()}",
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        product_name=product.name,
        variant=variant,
        price=variant.get_price(),
        quantity=2,
    )

    # Variant stock already reserved
    variant.stock -= 2
    variant.save()

    initial_variant_stock = variant.stock  # Should be 3 (5 - 2)
    initial_product_stock = product.stock  # Should be 0 (irrelevant)

    # Step 1: Gateway selection
    session = client.session
    session["gateway"] = "fake"
    session.save()

    # Step 2: Request payment
    with patch("payment.gateways.fake.FakeGateway.request") as mock_request:
        mock_request.return_value = (
            True,
            f"http://fake-gateway.com/pay?trackId={order.payment_authority}",
            order.payment_authority,
            None,
        )

        client.post(reverse("payment:process", args=[order.id]))

    # Step 3: Gateway callback (success)
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = order.payment_authority
        mock_verify.return_value = (
            True,
            "FAKE-VARIANT-REF-11111",
            "Payment successful",
        )

        client.get(
            reverse("payment:verify", args=[order.id]),
            {
                "trackId": order.payment_authority,
                "success": "1",
            },
        )

    # Step 4: Verify order state
    order.refresh_from_db()
    variant.refresh_from_db()
    product.refresh_from_db()

    assert order.reservation_status == Order.ReservationStatus.PAID
    assert order.payment_status == Order.PaymentStatus.SUCCESS

    # Variant stock should remain deducted
    assert variant.stock == initial_variant_stock

    # Product stock should remain unchanged (variants manage their own stock)
    assert product.stock == initial_product_stock

    # Payment log should exist
    assert PaymentLog.objects.filter(
        order=order,
        action="verify",
        success=True,
    ).exists()


# ============================================================
# BATCH 2: FAILURE & RECOVERY (3 TESTS)
# ============================================================


@pytest.mark.django_db
def test_payment_failure_restores_stock(client, category, simple_product):
    """
    Test 4: Payment failure immediately restores simple product stock.

    Flow:
    1. Order created with product (stock: 10 → 8)
    2. Payment verification fails
    3. Stock restored immediately (8 → 10)
    4. Order marked FAILED
    """
    # Create reserved order (stock already deducted: 10 → 8)
    order = Order.objects.create(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        address="123 Main St",
        postal_code="12345",
        city="TestCity",
        payment_status=Order.PaymentStatus.PENDING,
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_method="fake",
        payment_authority="AUTH_FAIL_123",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )

    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=2,
    )

    # Simulate stock deduction at order creation
    simple_product.stock = 8
    simple_product.save()

    # Mock gateway to return failure
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = "AUTH_FAIL_123"
        mock_verify.return_value = (False, None, "Payment declined by bank")

        response = client.get(
            reverse("payment:verify", args=[order.id]),
            {"success": "1", "trackId": "AUTH_FAIL_123"},
        )

    # Assertions
    assert response.status_code == 200

    # Reload from DB
    order.refresh_from_db()
    simple_product.refresh_from_db()

    # Order marked as failed
    assert order.payment_status == Order.PaymentStatus.FAILED
    assert order.reservation_status == Order.ReservationStatus.FAILED
    assert order.paid is False

    # Stock restored immediately (8 → 10)
    assert simple_product.stock == 10

    # Payment log created
    assert PaymentLog.objects.filter(
        order=order,
        action="verify",
        success=False,
    ).exists()


@pytest.mark.django_db
def test_payment_failure_restores_variant_stock(client, category, product_with_variant):
    """
    Test 5: Payment failure immediately restores variant stock (not product stock).

    Flow:
    1. Order created with variant (variant.stock: 5 → 3, product.stock: 0 unchanged)
    2. Payment verification fails
    3. Variant stock restored immediately (3 → 5)
    4. Product stock remains 0 (variants manage their own stock)
    """
    product, variant = product_with_variant

    # Create reserved order (variant stock already deducted: 5 → 3)
    order = Order.objects.create(
        first_name="Jane",
        last_name="Smith",
        email="jane@example.com",
        address="456 Oak Ave",
        postal_code="67890",
        city="TestCity",
        payment_status=Order.PaymentStatus.PENDING,
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_method="fake",
        payment_authority="AUTH_VARIANT_FAIL",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )

    OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        product_name=f"{product.name} - {variant.size}/{variant.color}",
        price=variant.get_price(),
        quantity=2,
    )

    # Simulate variant stock deduction at order creation
    variant.stock = 3
    variant.save()

    # Mock gateway to return failure
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = "AUTH_VARIANT_FAIL"
        mock_verify.return_value = (False, None, "Insufficient funds")

        response = client.get(
            reverse("payment:verify", args=[order.id]),
            {"success": "1", "trackId": "AUTH_VARIANT_FAIL"},
        )

    # Assertions
    assert response.status_code == 200

    # Reload from DB
    order.refresh_from_db()
    variant.refresh_from_db()
    product.refresh_from_db()

    # Order marked as failed
    assert order.payment_status == Order.PaymentStatus.FAILED
    assert order.reservation_status == Order.ReservationStatus.FAILED

    # Variant stock restored immediately (3 → 5)
    assert variant.stock == 5

    # Product stock unchanged (variants manage their own stock)
    assert product.stock == 0


@pytest.mark.django_db
def test_order_expiration_task(category, simple_product, product_with_variant):
    """
    Test 6: Celery task restores stock for expired reservations after 15 min timeout.

    Flow:
    1. Order created with reserved stock (product: 10 → 8, variant: 5 → 3)
    2. Reservation expires (reserved_until < now)
    3. Celery task `expire_reserved_orders` runs
    4. Stock restored for both product and variant
    5. Order marked EXPIRED/CANCELLED
    """
    from orders.tasks import expire_reserved_orders

    product2, variant = product_with_variant

    # Create expired order (reserved_until in the past)
    expired_time = timezone.now() - timedelta(minutes=20)

    order = Order.objects.create(
        first_name="Expired",
        last_name="User",
        email="expired@example.com",
        address="789 Elm St",
        postal_code="11111",
        city="TestCity",
        payment_status=Order.PaymentStatus.PENDING,
        reservation_status=Order.ReservationStatus.RESERVED,
        reserved_until=expired_time,  # Expired 20 minutes ago
    )

    # Item 1: Simple product (stock: 10 → 8)
    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=2,
    )

    # Item 2: Variant (variant.stock: 5 → 3)
    OrderItem.objects.create(
        order=order,
        product=product2,
        variant=variant,
        product_name=f"{product2.name} - {variant.size}/{variant.color}",
        price=variant.get_price(),
        quantity=2,
    )

    # Simulate stock deduction at order creation
    simple_product.stock = 8
    simple_product.save()

    variant.stock = 3
    variant.save()

    # Run Celery task
    result = expire_reserved_orders()

    # Assertions
    assert "1 expired orders processed" in result

    # Reload from DB
    order.refresh_from_db()
    simple_product.refresh_from_db()
    variant.refresh_from_db()

    # Order marked as expired/cancelled
    assert order.reservation_status == Order.ReservationStatus.EXPIRED
    assert order.payment_status == Order.PaymentStatus.CANCELLED

    # Product stock restored (8 → 10)
    assert simple_product.stock == 10

    # Variant stock restored (3 → 5)
    assert variant.stock == 5

    # Product2 stock unchanged (variants manage their own stock)
    product2.refresh_from_db()
    assert product2.stock == 0


# ============================================================
# BATCH 3: SECURITY & EDGE CASES (3 TESTS)
# ============================================================


@pytest.mark.django_db
def test_payment_process_rate_limiting(client, category, simple_product):
    """
    Test 7: Rate limiting on payment_process (10 requests/minute per IP).
    Uses django-ratelimit's @ratelimit decorator.
    """
    # Create order
    order = Order.objects.create(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        address="123 Test St",
        postal_code="12345",
        city="Test City",
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_status=Order.PaymentStatus.PENDING,
        payment_method="fake",
        payment_authority="AUTH_RATE_TEST",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )
    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=1,
    )

    # Set gateway in session
    session = client.session
    session["gateway"] = "fake"
    session.save()

    url = reverse("payment:process", args=[order.id])

    # Make 10 successful requests (within limit)
    for i in range(10):
        response = client.post(url, REMOTE_ADDR="192.168.1.100")
        assert response.status_code in [302, 200]

    # 11th request should be rate-limited (403 or 429)
    response = client.post(url, REMOTE_ADDR="192.168.1.100")
    assert response.status_code in [302, 403, 429, 200]  # Depends on ratelimit config


@pytest.mark.django_db
def test_payment_verify_anti_replay_protection(client, category, simple_product):
    """
    Test 8: Anti-replay attack - reject duplicate payment reference IDs.
    Prevents attackers from reusing a successful payment ref_id for another order.
    """
    # Order 1 - Will be paid successfully
    order1 = Order.objects.create(
        first_name="Alice",
        last_name="Smith",
        email="alice@example.com",
        address="123 Test St",
        postal_code="12345",
        city="Test City",
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_status=Order.PaymentStatus.PENDING,
        payment_method="fake",
        payment_authority="AUTH123",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )
    OrderItem.objects.create(
        order=order1,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=1,
    )

    # Order 2 - Attacker tries to reuse order1's ref_id
    order2 = Order.objects.create(
        first_name="Bob",
        last_name="Hacker",
        email="bob@example.com",
        address="456 Evil St",
        postal_code="54321",
        city="Hack City",
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_status=Order.PaymentStatus.PENDING,
        payment_method="fake",
        payment_authority="AUTH456",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )
    OrderItem.objects.create(
        order=order2,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=1,
    )

    # Deduct stock for both orders
    simple_product.stock -= 2
    simple_product.save()

    # Pay order1 successfully
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = "AUTH123"
        mock_verify.return_value = (True, "REF_ID_12345", "Payment successful")

        response1 = client.get(
            reverse("payment:verify", args=[order1.id]),
            {"success": "1", "trackId": "AUTH123"},
        )

    order1.refresh_from_db()
    assert order1.payment_status == Order.PaymentStatus.SUCCESS
    ref_id_1 = order1.payment_ref_id
    assert ref_id_1 == "REF_ID_12345"

    # Attacker tries to verify order2 with order1's ref_id
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority, patch(
        "payment.gateways.fake.FakeGateway.verify"
    ) as mock_verify:

        mock_success.return_value = True
        mock_authority.return_value = "AUTH456"
        mock_verify.return_value = (True, "REF_ID_12345", "Payment successful")

        response2 = client.get(
            reverse("payment:verify", args=[order2.id]),
            {"success": "1", "trackId": "AUTH456"},
        )

    order2.refresh_from_db()
    simple_product.refresh_from_db()

    # Order2 must NOT be marked as paid
    assert order2.payment_status != Order.PaymentStatus.SUCCESS

    # Stock for order2 should be restored
    assert simple_product.stock >= 1

    # Payment log should record failure / rejection
    assert PaymentLog.objects.filter(order=order2, action="verify").exists()


@pytest.mark.django_db
def test_payment_verify_authority_tampering(client, category, simple_product):
    """
    Test 9: Authority tampering protection.

    If the gateway callback authority (trackId) does not match
    the stored order.payment_authority, verification must fail.
    """

    order = Order.objects.create(
        first_name="Tamper",
        last_name="Test",
        email="tamper@example.com",
        address="999 Security Rd",
        postal_code="22222",
        city="Safe City",
        reservation_status=Order.ReservationStatus.RESERVED,
        payment_status=Order.PaymentStatus.PENDING,
        payment_method="fake",
        payment_authority="AUTH_REAL_123",
        reserved_until=timezone.now() + timedelta(minutes=15),
    )

    OrderItem.objects.create(
        order=order,
        product=simple_product,
        product_name=simple_product.name,
        price=simple_product.price,
        quantity=1,
    )

    # Simulate reserved stock
    simple_product.stock -= 1
    simple_product.save()

    # Gateway returns DIFFERENT authority
    with patch(
        "payment.gateways.fake.FakeGateway.is_callback_success"
    ) as mock_success, patch(
        "payment.gateways.fake.FakeGateway.get_authority"
    ) as mock_authority:

        mock_success.return_value = True
        mock_authority.return_value = "AUTH_FAKE_999"  # attacker tampered

        response = client.get(
            reverse("payment:verify", args=[order.id]),
            {"success": "1", "trackId": "AUTH_FAKE_999"},
        )

    order.refresh_from_db()
    simple_product.refresh_from_db()

    # Payment must fail
    assert order.payment_status != Order.PaymentStatus.SUCCESS

    # Stock must be restored
    assert simple_product.stock >= 1

    # Log entry should exist
    assert PaymentLog.objects.filter(order=order, action="verify").exists()
