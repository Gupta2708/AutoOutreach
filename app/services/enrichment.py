from __future__ import annotations

from app.clients.base import DecisionMakerClient, EmailResolverClient
from app.models import Company, Contact, EmailCandidate


async def discover_contacts(
    client: DecisionMakerClient,
    companies: list[Company],
    limit_per_company: int,
) -> list[Contact]:
    contacts: list[Contact] = []
    for company in companies:
        contacts.extend(await client.find_decision_makers(company, limit_per_company))
    return contacts


async def resolve_emails(
    client: EmailResolverClient,
    contacts: list[Contact],
) -> list[EmailCandidate]:
    candidates: list[EmailCandidate] = []
    for contact in contacts:
        candidates.append(await client.resolve_email(contact))
    return candidates
