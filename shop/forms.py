from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "rating": forms.RadioSelect(choices=[(i, f"{i}★") for i in range(1, 6)]),
            "comment": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": _(
                        "Share your experience with this product (optional)"
                    ),
                }
            ),
        }
        labels = {
            "rating": _("Your Rating"),
            "comment": _("Your Review"),
        }

    def clean_rating(self):
        rating = self.cleaned_data.get("rating")
        if rating and (rating < 1 or rating > 5):
            raise forms.ValidationError(_("Rating must be between 1 and 5."))
        return rating
