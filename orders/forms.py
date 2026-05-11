from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Order


class OrderCreateForm(forms.ModelForm):
    saved_address = forms.ChoiceField(
        choices=[],
        required=False,
        label=_("Select saved address"),
        widget=forms.Select(attrs={"id": "id_saved_address"}),
    )
    save_address = forms.BooleanField(
        required=False,
        initial=False,
        label=_("Save this address for future orders"),
    )

    class Meta:
        model = Order
        fields = [
            "first_name",
            "last_name",
            "email",
            "address",
            "postal_code",
            "city",
        ]
        labels = {
            "first_name": _("First name"),
            "last_name": _("Last name"),
            "email": _("Email"),
            "address": _("Address"),
            "postal_code": _("Postal code"),
            "city": _("City"),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user and user.is_authenticated:
            from accounts.models import Address

            addresses = Address.objects.filter(user=user)
            choices = [("", _("--- Select an address ---"))]
            choices += [(addr.id, f"{addr.label} - {addr.city}") for addr in addresses]
            self.fields["saved_address"].choices = choices
        else:
            self.fields["saved_address"].widget = forms.HiddenInput()
            self.fields["save_address"].widget = forms.HiddenInput()
