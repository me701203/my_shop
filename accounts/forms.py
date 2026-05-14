from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    PasswordResetForm,
)
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Address
import re

User = get_user_model()


class UserRegistrationForm(UserCreationForm):
    """Form for user registration"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control", "placeholder": "Email"}
        ),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Username"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"class": "form-control", "placeholder": "Confirm Password"}
        )


class UserLoginForm(AuthenticationForm):
    """Form for user login"""

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Username or Email"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        )
    )


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form"""

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"})
    )


class AddressForm(forms.ModelForm):
    """Form for creating and editing addresses"""

    class Meta:
        model = Address
        fields = [
            "label",
            "first_name",
            "last_name",
            "address",
            "postal_code",
            "city",
            "is_default",
        ]
        widgets = {
            "label": forms.TextInput(
                attrs={
                    "placeholder": "e.g., Home, Work",
                    "class": "form-control",
                }
            ),
            "first_name": forms.TextInput(
                attrs={
                    "placeholder": "First name",
                    "class": "form-control",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "placeholder": "Last name",
                    "class": "form-control",
                }
            ),
            "address": forms.TextInput(
                attrs={
                    "placeholder": "Street address",
                    "class": "form-control",
                }
            ),
            "postal_code": forms.TextInput(
                attrs={
                    "placeholder": "Postal code",
                    "class": "form-control",
                }
            ),
            "city": forms.TextInput(
                attrs={
                    "placeholder": "City",
                    "class": "form-control",
                }
            ),
        }

    def clean_label(self):
        """Validate address label"""
        label = self.cleaned_data.get("label")
        if label:
            label = label.strip()
            if len(label) < 2:
                raise ValidationError("Label must be at least 2 characters long.")
            if len(label) > 50:
                raise ValidationError("Label must be less than 50 characters.")
        return label

    def clean_first_name(self):
        """Validate first name"""
        first_name = self.cleaned_data.get("first_name")
        if first_name:
            first_name = first_name.strip()
            if not re.match(r"^[a-zA-Z\s\-']+$", first_name):
                raise ValidationError(
                    "First name can only contain letters, spaces, hyphens, and apostrophes."
                )
            if len(first_name) < 2:
                raise ValidationError("First name must be at least 2 characters long.")
        return first_name

    def clean_last_name(self):
        """Validate last name"""
        last_name = self.cleaned_data.get("last_name")
        if last_name:
            last_name = last_name.strip()
            if not re.match(r"^[a-zA-Z\s\-']+$", last_name):
                raise ValidationError(
                    "Last name can only contain letters, spaces, hyphens, and apostrophes."
                )
            if len(last_name) < 2:
                raise ValidationError("Last name must be at least 2 characters long.")
        return last_name

    def clean_address(self):
        """Validate address"""
        address = self.cleaned_data.get("address")
        if address:
            address = address.strip()
            if len(address) < 5:
                raise ValidationError("Address must be at least 5 characters long.")
            if len(address) > 250:
                raise ValidationError("Address must be less than 250 characters.")
        return address

    def clean_postal_code(self):
        postal_code = self.cleaned_data.get("postal_code", "").strip().upper()

        # Remove all spaces and hyphens for validation
        cleaned = postal_code.replace(" ", "").replace("-", "")

        # Must be 3-10 alphanumeric characters only (no special chars)
        if not re.match(r"^[A-Z0-9]{3,10}$", cleaned):
            raise forms.ValidationError(
                _(
                    "Postal code must contain only letters and numbers (3-10 characters)."
                )
            )

        # Optional: Add country-specific validation
        # Example for US ZIP codes:
        # if not re.match(r"^\d{5}$", cleaned):
        #     raise forms.ValidationError(_("Invalid US ZIP code format."))

        return postal_code  # Return original format for display

    def clean_city(self):
        """Validate city"""
        city = self.cleaned_data.get("city")
        if city:
            city = city.strip()
            if not re.match(r"^[a-zA-Z\s\-']+$", city):
                raise ValidationError(
                    "City name can only contain letters, spaces, hyphens, and apostrophes."
                )
            if len(city) < 2:
                raise ValidationError("City name must be at least 2 characters long.")
        return city

    def clean(self):
        cleaned_data = super().clean()
        label = cleaned_data.get("label")

        # Check for duplicate labels only if we have a user context
        if label:
            # For new addresses, check against the user passed to the form
            if hasattr(self, "user") and self.user:
                # Check if another address with this label exists for this user
                duplicate_check = Address.objects.filter(
                    user=self.user, label__iexact=label
                )
                # Exclude current instance if editing
                if self.instance.pk:
                    duplicate_check = duplicate_check.exclude(pk=self.instance.pk)

                if duplicate_check.exists():
                    self.add_error(
                        "label", "You already have an address with this label."
                    )

        # Validate first_name
        first_name = cleaned_data.get("first_name")
        if first_name:
            if len(first_name) < 2:
                self.add_error(
                    "first_name", "First name must be at least 2 characters."
                )
            if not re.match(r"^[a-zA-Z\s\-\']+$", first_name):
                self.add_error(
                    "first_name",
                    "First name can only contain letters, spaces, hyphens, and apostrophes.",
                )

        # Validate last_name
        last_name = cleaned_data.get("last_name")
        if last_name:
            if len(last_name) < 2:
                self.add_error("last_name", "Last name must be at least 2 characters.")
            if not re.match(r"^[a-zA-Z\s\-\']+$", last_name):
                self.add_error(
                    "last_name",
                    "Last name can only contain letters, spaces, hyphens, and apostrophes.",
                )

        # Validate address
        address = cleaned_data.get("address")
        if address and len(address) < 5:
            self.add_error("address", "Address must be at least 5 characters.")

        # Validate postal_code
        postal_code = cleaned_data.get("postal_code")
        if postal_code:
            # Adjust regex based on your country's postal code format
            # This example supports various formats (US, UK, Canada, etc.)
            if not re.match(r"^[A-Z0-9\s\-]{3,10}$", postal_code.upper()):
                self.add_error("postal_code", "Please enter a valid postal code.")

        # Validate city
        city = cleaned_data.get("city")
        if city:
            if len(city) < 2:
                self.add_error("city", "City name must be at least 2 characters.")
            if not re.match(r"^[a-zA-Z\s\-\']+$", city):
                self.add_error(
                    "city",
                    "City name can only contain letters, spaces, hyphens, and apostrophes.",
                )

        return cleaned_data
