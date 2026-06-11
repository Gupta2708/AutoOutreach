from __future__ import annotations

from app.models import Contact, EmailCandidate
from app.services.dedupe import dedupe_contacts, dedupe_email_candidates


def test_contact_dedupe_removes_duplicate_people() -> None:
    contact = Contact(
        first_name="Maya",
        last_name="Chen",
        full_name="Maya Chen",
        title="VP Sales",
        company_name="Acme",
        company_domain="acme.com",
        linkedin_url="https://linkedin.com/in/maya",
        source="test",
    )
    unique, duplicates = dedupe_contacts([contact, contact])
    assert unique == [contact]
    assert duplicates == 1


def test_email_dedupe_removes_duplicate_emails_case_insensitively() -> None:
    contact = Contact(company_domain="acme.com", source="test")
    first = EmailCandidate(contact=contact, email="maya@acme.com", status="verified", source="test")
    second = EmailCandidate(
        contact=contact,
        email="MAYA@acme.com",
        status="verified",
        source="test",
    )
    unique, duplicates = dedupe_email_candidates([first, second])
    assert unique == [first]
    assert duplicates == 1
