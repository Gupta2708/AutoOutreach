from __future__ import annotations

import re

from app.errors import ValidationError

DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?!-)(?:[a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,63}$"
)


def normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    domain = domain.removeprefix("https://").removeprefix("http://")
    domain = domain.removeprefix("www.")
    domain = domain.split("/", 1)[0].split("?", 1)[0].strip(".")
    if not DOMAIN_PATTERN.match(domain):
        raise ValidationError(f"Invalid domain: {value}")
    return domain


def is_valid_email(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value))
