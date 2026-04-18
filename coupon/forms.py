from django import forms


class CouponApplyForm(forms.Form):
    code = forms.CharField(
        label="",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter coupon code",
            }
        ),
    )
