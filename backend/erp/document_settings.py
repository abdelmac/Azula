"""Présentation limitée à des options explicites, sans HTML ni CSS arbitraire."""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def validate_print_settings(value):
    if not isinstance(value, dict) or set(value) - {
        "layout", "accent", "footer", "show_product_codes", "show_tax", "payment_details", "logo_url",
    }:
        raise ValidationError("invalid_input")
    for name, item in value.items():
        if name == "layout":
            valid = item in ("standard", "compact")
        elif name == "accent":
            valid = isinstance(item, str) and bool(re.fullmatch(r"#[0-9a-fA-F]{6}", item))
        elif name in {"show_product_codes", "show_tax"}:
            valid = isinstance(item, bool)
        else:
            valid = isinstance(item, str) and len(item) <= (1000 if name == "logo_url" else 2000)
            if valid and name == "logo_url" and item:
                URLValidator(schemes=["https"])(item)
                parsed = urlsplit(item)
                valid = parsed.username is None and parsed.password is None
        if not valid:
            raise ValidationError("invalid_input")
    return value
