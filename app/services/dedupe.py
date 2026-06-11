from __future__ import annotations

from app.models import Contact, EmailCandidate


def _contact_key(contact: Contact) -> tuple[str, str, str]:
    name = (contact.full_name or f"{contact.first_name or ''} {contact.last_name or ''}").strip()
    linkedin = contact.linkedin_url or ""
    return (name.lower(), contact.company_domain.lower(), linkedin.lower())


def dedupe_contacts(contacts: list[Contact]) -> tuple[list[Contact], int]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[Contact] = []
    duplicates = 0
    for contact in contacts:
        key = _contact_key(contact)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(contact)
    return unique, duplicates


def dedupe_email_candidates(
    candidates: list[EmailCandidate],
) -> tuple[list[EmailCandidate], int]:
    seen_emails: set[str] = set()
    unique: list[EmailCandidate] = []
    duplicates = 0
    for candidate in candidates:
        if not candidate.email:
            unique.append(candidate)
            continue
        key = candidate.email.lower()
        if key in seen_emails:
            duplicates += 1
            continue
        seen_emails.add(key)
        unique.append(candidate)
    return unique, duplicates
