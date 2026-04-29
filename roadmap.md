0. Foundations (Completed)
✔ Cart system

✔ Orders

✔ Checkout

✔ Payment

✔ Stock reduction

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

1. Core Product Logic Fixes (CURRENT TASK GROUP)
1.1 Stock‑safe + Variant‑safe category filtering
Status: NEXT

Goal: Category page must show only products that are actually available considering:

• product stock

• variant stock

• auto-availability rules

1.2 Strengthen availability rules for variants
Status: AFTER 1.1

Goal:

Product.available = True if either:

• product.stock > 0

• any variant.stock > 0

1.3 Improve product list caching
Status: SOON

Goal:

• Per-category cache

• Per-product cache invalidation

• Variant-aware invalidation

• Faster frontend

1.4 Availability sync migration
Status: READY (run when you want)

File: 0005_sync_availability.py

Fixes old inconsistent availability states.

2. Media/Image Pipeline (Performance Upgrade)
2.1 Automatically compress images
2.2 Automatically resize images
2.3 Auto-generate thumbnails
2.4 Serve responsive images
2.5 Dramatically speed up product & category views
3. Variant UX Implementation
3.1 Beautiful variant selectors (size/color dropdowns)
3.2 Dynamic price loading per variant
3.3 Add-to-cart variant support
3.4 Show selected variant in cart and order
3.5 Variant stock validation
4. Improved Recommendation Engine
Better than the basic book version:

• Real similarity scores

• Track product views

• Track orders

• Track add-to-cart events

• Cached recommendations

5. PostgreSQL Full‑Text Search
• Weighted search (name > description > category)

• Search indexes

• Highlighting

• Autocomplete

• Related queries

6. Discount & Coupon System
• Percentage off

• Fixed amount off

• Date validity

• Minimum cart value

• Per-category coupons

• Per-user coupons

7. Reviews & Ratings
• Verified customers only

• Rating stars

• Display rating avg

• Admin moderation

• Helpfulness voting

8. Optional Future Expansions
• CMS

• Tagging system

• Marketplace + multiple sellers

• REST API (Chapter 15)

• Mobile app backend

• Realtime notifications (Channels)

• Docker/Nginx full production environment