from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from shop.models import Product, ProductVariant


class CartAddProductForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(
            attrs={"class": "quantity-input", "style": "width:60px; padding:4px;"}
        ),
    )
    override = forms.BooleanField(
        required=False, initial=False, widget=forms.HiddenInput
    )
    variant_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.product = kwargs.pop("product", None)
        self.cart = kwargs.pop("cart", None)
        super().__init__(*args, **kwargs)

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")

        if quantity <= 0:
            raise ValidationError(_("Quantity must be positive."))

        return quantity

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get("quantity")
        variant_id = cleaned_data.get("variant_id")

        if not self.product or not quantity:
            return cleaned_data

        # Get available stock
        if variant_id:
            try:
                variant = ProductVariant.objects.get(
                    id=variant_id, product=self.product
                )
                available_stock = variant.stock
            except ProductVariant.DoesNotExist:
                raise ValidationError(_("Invalid variant selected."))
        else:
            available_stock = self.product.stock

        # Check against cart if provided
        if self.cart:
            current_in_cart = self.cart.get_current_quantity(
                self.product.id, variant_id
            )

            # If not overriding, add to existing quantity
            if not cleaned_data.get("override"):
                total_requested = current_in_cart + quantity
            else:
                total_requested = quantity

            if total_requested > available_stock:
                raise ValidationError(
                    _(
                        "Not enough stock. Available: %(stock)s, requested: %(requested)s"
                    )
                    % {"stock": available_stock, "requested": total_requested}
                )
        else:
            # Simple check without cart context
            if quantity > available_stock:
                raise ValidationError(
                    _("Not enough stock. Available: %(stock)s")
                    % {"stock": available_stock}
                )

        return cleaned_data
