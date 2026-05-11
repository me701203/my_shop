from django import template
from django.conf import settings
from django.utils import translation

register = template.Library()

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(value: str) -> str:
    return value.translate(PERSIAN_DIGITS)


@register.filter
def currency(value):
    """
    Language-aware currency formatting

    EN → 2,500 Toman
    FA → ۲٬۵۰۰ تومان
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return value

    formatted = f"{amount:,.0f}"

    lang = translation.get_language() or "en"

    # convert digits for Persian
    if lang.startswith("fa"):
        formatted = to_persian_digits(formatted)

    # get symbol from settings
    symbols = getattr(settings, "CURRENCY_SYMBOLS", {})
    symbol = symbols.get(lang[:2], symbols.get("en", ""))

    return f"{formatted} {symbol}"


@register.filter
def split(value, delimiter=","):
    return value.split(delimiter)
