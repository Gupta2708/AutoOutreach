from __future__ import annotations

import pytest

from app.errors import ValidationError
from app.services.validators import normalize_domain


def test_normalize_domain_accepts_urls() -> None:
    assert normalize_domain("https://www.Example.com/path") == "example.com"


def test_normalize_domain_rejects_invalid_domains() -> None:
    with pytest.raises(ValidationError):
        normalize_domain("not a domain")
