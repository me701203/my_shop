# utils/numbers.py

import re

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ENGLISH_DIGITS = "0123456789"


def convert_digits(text, to_persian=False):
    """Convert numbers in text between English ↔ Persian"""
    if not text:
        return text
    mapping = str.maketrans(
        ENGLISH_DIGITS + PERSIAN_DIGITS,
        (PERSIAN_DIGITS if to_persian else ENGLISH_DIGITS) * 2,
    )
    return text.translate(mapping)
