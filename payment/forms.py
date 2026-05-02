from django import forms
from payment.models import Refund


class RefundCreateForm(forms.ModelForm):

    class Meta:
        model = Refund
        fields = ["amount", "reason"]
