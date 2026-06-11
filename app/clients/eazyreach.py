from __future__ import annotations

from app.clients.base import BaseAPIClient
from app.models import Contact, EmailCandidate


class EazyreachClient(BaseAPIClient):
    def __init__(self, *, api_key: str, timeout_seconds: float, max_retries: int) -> None:
        super().__init__(
            base_url="https://api.eazyreach.io",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def resolve_email(self, contact: Contact) -> EmailCandidate:
        # TODO: Replace placeholder path with Eazyreach's current enrichment endpoint.
        data = await self.request(
            "POST",
            "/v1/email/resolve",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "full_name": contact.full_name,
                "domain": contact.company_domain,
                "linkedin_url": contact.linkedin_url,
            },
        )
        status = data.get("status") or "unknown"
        if status not in {"verified", "risky", "not_found", "unknown"}:
            status = "unknown"
        return EmailCandidate(
            contact=contact,
            email=data.get("email"),
            status=status,
            confidence=data.get("confidence"),
            source="eazyreach",
        )
