from django.db import migrations


def sync_availability(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    for p in Product.objects.all():
        # If stock <= 0 → product should not be available
        if p.stock <= 0 and p.available:
            p.available = False
            p.save(update_fields=["available"])

        # If stock > 0 → product should be available
        elif p.stock > 0 and not p.available:
            p.available = True
            p.save(update_fields=["available"])


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0004_productvariant"),
    ]

    operations = [
        migrations.RunPython(sync_availability, migrations.RunPython.noop),
    ]
