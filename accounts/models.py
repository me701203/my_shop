from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Custom user model"""

    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.username


class Address(models.Model):
    """Model for storing user addresses"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(
        max_length=50,
        help_text=_("e.g., Home, Work, Office"),
        verbose_name=_("Address Label"),
    )
    first_name = models.CharField(max_length=50, verbose_name=_("First name"))
    last_name = models.CharField(max_length=50, verbose_name=_("Last name"))
    address = models.CharField(max_length=250, verbose_name=_("Address"))
    postal_code = models.CharField(max_length=20, verbose_name=_("Postal code"))
    city = models.CharField(max_length=100, verbose_name=_("City"))
    is_default = models.BooleanField(
        default=False, verbose_name=_("Set as default address")
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")
        ordering = ["-is_default", "-created"]

    def __str__(self):
        return f"{self.label} - {self.city}"

    def save(self, *args, **kwargs):
        # If this address is set as default, unset other default addresses
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).update(
                is_default=False
            )
        super().save(*args, **kwargs)
