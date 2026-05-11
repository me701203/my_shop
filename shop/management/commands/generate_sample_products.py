from django.core.management.base import BaseCommand
from django.utils.text import slugify
from shop.models import Category, Product, ProductVariant
from decimal import Decimal


class Command(BaseCommand):
    help = "Generate sample products with and without variants"

    def handle(self, *args, **options):
        # Create categories
        electronics, _ = Category.objects.get_or_create(
            slug="electronics", defaults={"name": "Electronics"}
        )
        electronics.set_current_language("en")
        electronics.name = "Electronics"
        electronics.save()
        electronics.set_current_language("fa")
        electronics.name = "الکترونیک"
        electronics.save()

        clothing, _ = Category.objects.get_or_create(
            slug="clothing", defaults={"name": "Clothing"}
        )
        clothing.set_current_language("en")
        clothing.name = "Clothing"
        clothing.save()
        clothing.set_current_language("fa")
        clothing.name = "پوشاک"
        clothing.save()

        books, _ = Category.objects.get_or_create(
            slug="books", defaults={"name": "Books"}
        )
        books.set_current_language("en")
        books.name = "Books"
        books.save()
        books.set_current_language("fa")
        books.name = "کتاب"
        books.save()

        # Products WITHOUT variants
        simple_products = [
            {
                "name_en": "Wireless Mouse",
                "name_fa": "ماوس بی‌سیم",
                "desc_en": "Ergonomic wireless mouse with 2.4GHz connection",
                "desc_fa": "ماوس بی‌سیم ارگونومیک با اتصال 2.4 گیگاهرتز",
                "category": electronics,
                "price": Decimal("29.99"),
                "stock": 50,
            },
            {
                "name_en": "USB-C Cable",
                "name_fa": "کابل USB-C",
                "desc_en": "Fast charging USB-C cable, 2 meters",
                "desc_fa": "کابل USB-C شارژ سریع، 2 متری",
                "category": electronics,
                "price": Decimal("12.99"),
                "stock": 100,
            },
            {
                "name_en": "Python Programming Book",
                "name_fa": "کتاب برنامه‌نویسی پایتون",
                "desc_en": "Complete guide to Python programming for beginners",
                "desc_fa": "راهنمای کامل برنامه‌نویسی پایتون برای مبتدیان",
                "category": books,
                "price": Decimal("39.99"),
                "stock": 25,
            },
            {
                "name_en": "Django Web Development",
                "name_fa": "توسعه وب با جنگو",
                "desc_en": "Master Django framework with practical examples",
                "desc_fa": "تسلط بر فریمورک جنگو با مثال‌های کاربردی",
                "category": books,
                "price": Decimal("45.00"),
                "stock": 15,
            },
        ]

        for data in simple_products:
            slug = slugify(data["name_en"])
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={
                    "category": data["category"],
                    "price": data["price"],
                    "stock": data["stock"],
                    "available": True,
                },
            )

            product.set_current_language("en")
            product.name = data["name_en"]
            product.description = data["desc_en"]
            product.save()

            product.set_current_language("fa")
            product.name = data["name_fa"]
            product.description = data["desc_fa"]
            product.save()

            self.stdout.write(self.style.SUCCESS(f'✓ Created: {data["name_en"]}'))

        # Products WITH variants
        # T-Shirt with size and color variants
        tshirt, created = Product.objects.get_or_create(
            slug="cotton-t-shirt",
            defaults={
                "category": clothing,
                "price": Decimal("19.99"),  # Base price
                "stock": 0,  # Stock managed by variants
                "available": True,
            },
        )
        tshirt.set_current_language("en")
        tshirt.name = "Cotton T-Shirt"
        tshirt.description = "Comfortable 100% cotton t-shirt"
        tshirt.save()
        tshirt.set_current_language("fa")
        tshirt.name = "تی‌شرت نخی"
        tshirt.description = "تی‌شرت راحت 100% پنبه"
        tshirt.save()

        sizes = ["S", "M", "L", "XL"]
        colors = ["Red", "Blue", "Black", "White"]

        for size in sizes:
            for color in colors:
                ProductVariant.objects.get_or_create(
                    product=tshirt,
                    size=size,
                    color=color,
                    defaults={"stock": 10, "price_override": None},
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Created: Cotton T-Shirt with {len(sizes) * len(colors)} variants"
            )
        )

        # Sneakers with size variants only
        sneakers, created = Product.objects.get_or_create(
            slug="running-sneakers",
            defaults={
                "category": clothing,
                "price": Decimal("79.99"),
                "stock": 0,
                "available": True,
            },
        )
        sneakers.set_current_language("en")
        sneakers.name = "Running Sneakers"
        sneakers.description = "Lightweight running shoes with cushioned sole"
        sneakers.save()
        sneakers.set_current_language("fa")
        sneakers.name = "کفش ورزشی"
        sneakers.description = "کفش دویدن سبک با کف کشدار"
        sneakers.save()

        shoe_sizes = ["38", "39", "40", "41", "42", "43", "44"]

        for size in shoe_sizes:
            ProductVariant.objects.get_or_create(
                product=sneakers,
                size=size,
                color="",
                defaults={"stock": 5, "price_override": None},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Created: Running Sneakers with {len(shoe_sizes)} size variants"
            )
        )

        # Laptop with color variants and different prices
        laptop, created = Product.objects.get_or_create(
            slug="ultrabook-laptop",
            defaults={
                "category": electronics,
                "price": Decimal("999.00"),
                "stock": 0,
                "available": True,
            },
        )
        laptop.set_current_language("en")
        laptop.name = "Ultrabook Laptop"
        laptop.description = "14-inch ultrabook with SSD and 16GB RAM"
        laptop.save()
        laptop.set_current_language("fa")
        laptop.name = "لپ‌تاپ اولترابوک"
        laptop.description = "اولترابوک 14 اینچی با SSD و 16 گیگابایت رم"
        laptop.save()

        laptop_variants = [
            {"color": "Silver", "stock": 8, "price": Decimal("999.00")},
            {"color": "Space Gray", "stock": 5, "price": Decimal("1049.00")},
            {"color": "Rose Gold", "stock": 3, "price": Decimal("1099.00")},
        ]

        for variant in laptop_variants:
            ProductVariant.objects.get_or_create(
                product=laptop,
                size="",
                color=variant["color"],
                defaults={
                    "stock": variant["stock"],
                    "price_override": variant["price"],
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Created: Ultrabook Laptop with {len(laptop_variants)} color variants"
            )
        )

        # Product with ZERO stock for testing alerts
        zero_stock_product, created = Product.objects.get_or_create(
            slug="out-of-stock-test",
            defaults={
                "category": electronics,
                "price": Decimal("99.99"),
                "stock": 0,  # Zero stock
                "available": True,
            },
        )
        zero_stock_product.set_current_language("en")
        zero_stock_product.name = "Out of Stock Test Product"
        zero_stock_product.description = (
            "This product is out of stock for testing stock alerts"
        )
        zero_stock_product.save()
        zero_stock_product.set_current_language("fa")
        zero_stock_product.name = "محصول تست موجودی صفر"
        zero_stock_product.description = "این محصول برای تست هشدار موجودی ناموجود است"
        zero_stock_product.save()

        self.stdout.write(
            self.style.WARNING(f"⚠ Created: Out of Stock Test Product (stock=0)")
        )

        # Product WITH variants but ALL variants have zero stock
        zero_variant_product, created = Product.objects.get_or_create(
            slug="zero-variant-test",
            defaults={
                "category": clothing,
                "price": Decimal("49.99"),
                "stock": 0,
                "available": True,
            },
        )
        zero_variant_product.set_current_language("en")
        zero_variant_product.name = "Zero Stock Variant Test"
        zero_variant_product.description = "Product with variants, all out of stock"
        zero_variant_product.save()
        zero_variant_product.set_current_language("fa")
        zero_variant_product.name = "تست واریانت موجودی صفر"
        zero_variant_product.description = "محصول با واریانت‌ها، همه ناموجود"
        zero_variant_product.save()

        # Create variants with zero stock
        for size in ["S", "M", "L"]:
            ProductVariant.objects.get_or_create(
                product=zero_variant_product,
                size=size,
                color="Black",
                defaults={"stock": 0, "price_override": None},
            )

        self.stdout.write(
            self.style.WARNING(
                f"⚠ Created: Zero Stock Variant Test with 3 variants (all stock=0)"
            )
        )

        self.stdout.write(
            self.style.SUCCESS("\n✅ Sample products generated successfully!")
        )
