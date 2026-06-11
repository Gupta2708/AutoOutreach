from __future__ import annotations

from app.models import Contact, EmailCandidate
from app.services.email_copy import EmailCopyService


def test_email_copy_generation_is_deterministic() -> None:
    contact = Contact(
        first_name="Maya",
        last_name="Chen",
        full_name="Maya Chen",
        title="VP Sales",
        company_name="Acme",
        company_domain="acme.com",
        source="test",
    )
    candidate = EmailCandidate(
        contact=contact,
        email="maya@acme.com",
        status="verified",
        confidence=0.95,
        source="test",
    )
    service = EmailCopyService()

    first = service.generate(candidate)
    second = service.generate(candidate)

    assert first is not None
    assert second is not None
    assert first.subject == second.subject
    assert "Acme" in first.text_body
    assert "VP Sales" in first.text_body
