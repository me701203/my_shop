from django import template
from django.conf import settings

register = template.Library()

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(value: str) -> str:
    return value.translate(PERSIAN_DIGITS)


@register.filter
def currency(value):
    """
    Format numbers like:
      2500 → ۲٬۵۰۰ تومان
    """
    try:
        # Convert to float or decimal
        amount = float(value)
    except (TypeError, ValueError):
        return value

    # Format with comma separators
    formatted = f"{amount:,.0f}"  # remove decimals

    # Convert to Persian digits
    formatted = to_persian_digits(formatted)

    # Add currency symbol from settings
    symbol = getattr(settings, "CURRENCY_SYMBOL", "")

    return f"{formatted} {symbol}"
