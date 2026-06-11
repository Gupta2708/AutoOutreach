from __future__ import annotations

from app.models import Company, Contact, EmailCandidate, OutreachEmail, SendResult


class MockDiscoveryClient:
    async def discover_similar_companies(self, seed_domain: str, limit: int) -> list[Company]:
        domains = [
            ("Northstar CRM", "northstarcrm.com", 0.92),
            ("RelayDesk", "relaydesk.io", 0.88),
            ("BrightLoop", "brightloop.ai", 0.83),
            ("SignalNest", "signalnest.co", 0.79),
            ("OrbitOps", "orbitops.com", 0.75),
        ]
        return [
            Company(name=name, domain=domain, source="mock", similarity_score=score)
            for name, domain, score in domains[: max(limit, 5)]
        ][:5]


class MockProspeoClient:
    async def find_decision_makers(self, company: Company, limit: int) -> list[Contact]:
        base = [
            ("Maya", "Chen", "Maya Chen", "VP Sales", "https://linkedin.com/in/mayachen"),
            ("Sam", "Patel", "Sam Patel", "Founder", None),
            ("Jordan", "Lee", "Jordan Lee", "Head of Growth", "https://linkedin.com/in/jordanlee"),
        ]
        contacts = [
            Contact(
                first_name=first,
                last_name=last,
                full_name=full,
                title=title,
                company_name=company.name,
                company_domain=company.domain,
                linkedin_url=linkedin,
                source="mock-prospeo",
            )
            for first, last, full, title, linkedin in base[: min(limit, 3)]
        ]
        if company.domain in {"relaydesk.io", "signalnest.co"}:
            contacts.append(contacts[0])
        return contacts

    async def resolve_email(self, contact: Contact) -> EmailCandidate:
        return await MockEmailResolverClient().resolve_email(contact)


class MockEmailResolverClient:
    async def resolve_email(self, contact: Contact) -> EmailCandidate:
        first = (contact.first_name or "info").lower()
        last = (contact.last_name or "").lower()
        if first == "jordan":
            return EmailCandidate(contact=contact, email=None, status="not_found", source="mock")
        if first == "sam":
            return EmailCandidate(
                contact=contact,
                email=f"{first}.{last}@{contact.company_domain}",
                status="risky",
                confidence=0.58,
                source="mock",
            )
        return EmailCandidate(
            contact=contact,
            email=f"{first}.{last}@{contact.company_domain}",
            status="verified",
            confidence=0.94,
            source="mock",
        )


class MockBrevoClient:
    async def send_email(self, outreach_email: OutreachEmail) -> SendResult:
        if outreach_email.to_email.endswith("@relaydesk.io"):
            return SendResult(
                email=outreach_email.to_email,
                status="failed",
                provider_message_id=None,
                error="Mock send failure for demo resilience.",
            )
        return SendResult(
            email=outreach_email.to_email,
            status="sent",
            provider_message_id=f"mock-{outreach_email.to_email}",
            error=None,
        )
