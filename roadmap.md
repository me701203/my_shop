Ecommerce System Roadmap
0. Foundations ✅ COMPLETED
✔ Cart system

✔ Orders

✔ Checkout

✔ Payment gateways

✔ Payment verification safety

✔ Stock reservation system

✔ Stock validation

✔ Multilingual support

✔ django-parler translation system

✔ Frontend messages & UX fixes

✔ Category & product admin polish

✔ ProductVariant model

✔ Variant translations

✔ Initial caching (basic)

✔ Error message improvements

✔ Availability migration prepared (0005_sync_availability.py)

Additional Completed Systems
✔ Order fulfillment statuses

✔ Shipment tracking system

✔ Payment logging system

✔ Invoice PDF generation

✔ Coupon system

✔ Item-level order cancellation

✔ Item-level refund system

✔ Refund approval workflow

✔ RefundGuard validation service

✔ Staff refund interface

✔ Financial audit trail via PaymentLog

1. Core Product Logic Fixes
1.1 Stock‑safe + Variant‑safe category filtering
Status: NEXT

Goal:

Category page must show only products that are actually available considering:

• product stock

• variant stock

• auto-availability rules

1.2 Strengthen availability rules for variants
Status: AFTER 1.1

Goal:

text
Product.available = True if either:

product.stock > 0
OR
any variant.stock > 0
1.3 Improve product list caching
Status: SOON

Goal:

• Per-category cache

• Per-product cache invalidation

• Variant-aware invalidation

• Faster frontend

1.4 Availability sync migration
Status: READY

File:

text
0005_sync_availability.py
Purpose:

Fix old inconsistent availability states.

2. Media/Image Pipeline (Performance Upgrade)
Goals:

• Automatically compress images

• Automatically resize images

• Auto-generate thumbnails

• Serve responsive images

• Dramatically speed up product & category views

3. Variant UX Implementation
Goals:

• Beautiful variant selectors (size/color dropdowns)

• Dynamic price loading per variant

• Add-to-cart variant support

• Show selected variant in cart and order

• Variant stock validation

4. Improved Recommendation Engine
Upgrade recommender system to track behavior.

Features:

• Real similarity scores

• Track product views

• Track orders

• Track add-to-cart events

• Cached recommendations

5. PostgreSQL Full‑Text Search
Goals:

• Weighted search

text
name > description > category
• Search indexes

• Highlighting

• Autocomplete

• Related queries

6. Discount & Coupon System ✅ PARTIALLY IMPLEMENTED
Implemented:

✔ Coupon model

✔ Order discount support

✔ Coupon usage tracking

Planned improvements:

• Percentage off

• Fixed amount off

• Date validity

• Minimum cart value

• Per-category coupons

• Per-user coupons

7. Reviews & Ratings
Features:

• Verified customers only

• Rating stars

• Display rating average

• Admin moderation

• Helpfulness voting

8. Operational Systems (Enterprise Features)
A. Customer Account System
Features:

• Order history

• Refund status

• Invoice downloads

B. Order Event Timeline (Major Architecture Upgrade)
Central order history system.

Tracks:

• Order created

• Payment success

• Item cancelled

• Refund issued

• Shipment sent

• Delivery confirmed

Used for:

• Admin debugging

• Customer order timeline

• Analytics

• Notifications

C. Staff Operations Dashboard
Operations control center.

Displays:

• Pending orders

• Refund requests

• Shipment queue

• Payment failures

D. Return / RMA System
Full return management system.

Workflow:

text
Customer requests return
↓
Staff reviews request
↓
Return approved
↓
Customer ships item back
↓
Item received
↓
Refund issued
Required for professional ecommerce.

9. Optional Future Expansions
• CMS

• Tagging system

• Marketplace (multi-seller)

• REST API

• Mobile app backend

• Realtime notifications (Django Channels)

• Docker + Nginx production deployment

action plan regarding this roadmap:

Phase 1: Fix Critical Bugs (Do This First)
Fix variant stock restoration in expire_reserved_orders ⚠️
Add idempotency check in payment_verify ⚠️
Fix coupon usage increment timing ⚠️
Add rate limiting to payment endpoints ⚠️
Add webhook signature verification (if using real gateways) ⚠️
Phase 2: Complete Roadmap Section 1 (Core Logic)
Implement stock-safe category filtering
Fix variant availability auto-update
Run availability sync migration
Improve product list caching
Phase 3: UX Improvements
Add variant selectors to product pages
Add search functionality
Optimize images (compression + thumbnails)
Phase 4: Customer Features
Add customer order history
Add order event timeline
Add reviews/ratings
Phase 5: Production Readiness
Switch to PostgreSQL
Add proper logging (Sentry)
Add monitoring
Write tests
Set up CI/CD

Key Dependencies by Feature
Feature	Required Files	Models Touched
Order with Product (no variant)	orders/models.py, shop/models.py	Order, OrderItem, Product
Order with ProductVariant	orders/models.py, shop/models.py	Order, OrderItem, Product, ProductVariant
Coupon Application	coupon/models.py, orders/models.py	Coupon, Order
Payment Request	payment/views.py, payment/gateways/*.py, payment/models.py	Order, PaymentLog
Payment Verify (Success)	payment/views.py, payment/gateways/*.py, orders/models.py, coupon/models.py	Order, OrderItem, Coupon, PaymentLog, Product/ProductVariant
Payment Verify (Failure)	payment/views.py, payment/gateways/*.py, shop/models.py	Order, Product/ProductVariant, PaymentLog
Order Expiration	orders/tasks.py, orders/models.py, shop/models.py	Order, OrderItem, Product/ProductVariant
Rate Limiting	payment/views.py (django-ratelimit decorator)	None (HTTP response only)
Refund	payment/views.py, payment/models.py, orders/models.py	Refund, OrderItem, Order, PaymentLog

Critical Test Scenarios (What We Need to Cover)
Scenario	Gateway	Expected Behavior	Files Needed
Simple order, no coupon, payment success	Fake	Stock stays reduced, order paid	payment/views.py, shop/models.py, orders/models.py
Order with coupon, payment success	Fake	Coupon.uses += 1 (once only)	+ coupon/models.py
Order with variant, payment success	Fake	Variant stock stays reduced	+ shop/models.py (ProductVariant)
Payment failure	Fake	Stock restored immediately	All above
Order expiration (15 min timeout)	N/A	Stock restored by Celery task	+ orders/tasks.py
Rate limiting (>10 requests/min)	Fake	Returns 429	payment/views.py only
Idempotency (revisit success URL)	Fake	No double-processing	payment/views.py, orders/models.py
Anti-replay (reuse ref_id)	Fake	Rejected	payment/views.py, orders/models.py
Authority tampering	Fake	Rejected	payment/views.py

Test Suite Structure (9 tests total, 3 batches)
Batch 1: Core Payment Success Flows (Foundation)
test_simple_order_payment_success - Simple product, no coupon, fake gateway success
test_order_with_coupon_payment_success - Verify coupon increments once only
test_order_with_variant_payment_success - Variant stock handling
Batch 2: Failure & Recovery (Stock restoration)
test_payment_failure_restores_stock - Product stock restored on payment failure
test_payment_failure_restores_variant_stock - Variant stock restored on payment failure
test_order_expiration_task - Celery task restores stock after 15 min timeout
Batch 3: Security & Edge Cases (Anti-abuse)
test_rate_limiting_returns_429 - Rate limit protection
test_idempotency_prevents_double_processing - Revisiting success URL
test_anti_replay_rejects_reused_ref_id - Payment reference reuse blocked