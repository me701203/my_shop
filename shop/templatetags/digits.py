from django import template
from django.utils.translation import get_language

register = template.Library()

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"


def convert_to_persian(num_str):
    return "".join(
        PERSIAN_DIGITS[ENGLISH_DIGITS.index(ch)] if ch in ENGLISH_DIGITS else ch
        for ch in str(num_str)
    )


@register.filter
def smart_digits(value):
    """
    Converts digits ONLY if current language starts with 'fa'.
    Works for 'fa', 'fa-ir', 'fa-IR', etc.
    """
    lang = get_language()

    if lang and lang.lower().startswith("fa"):
        return convert_to_persian(value)

    return str(value)
