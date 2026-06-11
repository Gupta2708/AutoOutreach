from __future__ import annotations

from typing import Any

from app.clients.base import BaseAPIClient
from app.errors import ProviderHTTPError
from app.models import Company, Contact, EmailCandidate


class ProspeoClient(BaseAPIClient):
    def __init__(self, *, api_key: str, timeout_seconds: float, max_retries: int) -> None:
        super().__init__(
            base_url="https://api.prospeo.io",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    async def find_decision_makers(self, company: Company, limit: int) -> list[Contact]:
        data = await self.request(
            "POST",
            "/search-person",
            headers=self._headers(),
            json={
                "page": 1,
                "filters": {
                    "company": {
                        "websites": {
                            "include": [company.domain],
                        }
                    },
                    "person_seniority": {
                        "include": [
                            "Founder/Owner",
                            "C-Suite",
                            "Vice President",
                            "Head",
                            "Director",
                        ]
                    },
                },
            },
        )
        self._raise_if_error(data)
        rows = data.get("results") or []
        contacts: list[Contact] = []
        for row in rows[:limit]:
            person = row.get("person") or {}
            result_company = row.get("company") or {}
            contacts.append(
                Contact(
                    first_name=person.get("first_name"),
                    last_name=person.get("last_name"),
                    full_name=person.get("full_name"),
                    title=person.get("current_job_title") or person.get("headline"),
                    company_name=result_company.get("name") or company.name,
                    company_domain=(
                        result_company.get("domain")
                        or _domain_from_website(result_company.get("website"))
                        or company.domain
                    ),
                    linkedin_url=person.get("linkedin_url"),
                    source=f"prospeo:{person.get('person_id') or 'search'}",
                )
            )
        return contacts

    async def resolve_email(self, contact: Contact) -> EmailCandidate:
        person_id = _source_id(contact.source)
        payload_data: dict[str, Any] = {"company_website": contact.company_domain}
        if person_id:
            payload_data["person_id"] = person_id
        elif contact.linkedin_url:
            payload_data["linkedin_url"] = contact.linkedin_url
        elif contact.first_name and contact.last_name:
            payload_data.update(
                {
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                }
            )
        elif contact.full_name:
            payload_data["full_name"] = contact.full_name
        else:
            return EmailCandidate(contact=contact, email=None, status="unknown", source="prospeo")

        data = await self.request(
            "POST",
            "/enrich-person",
            headers=self._headers(),
            json={
                "only_verified_email": True,
                "enrich_mobile": False,
                "data": payload_data,
            },
        )
        if data.get("error"):
            return EmailCandidate(
                contact=contact,
                email=None,
                status="not_found" if data.get("error_code") == "NO_MATCH" else "unknown",
                confidence=None,
                source="prospeo",
            )

        person = data.get("person") or {}
        email_info = person.get("email") or {}
        email = email_info.get("email")
        status = _map_email_status(email_info.get("status"), email)
        return EmailCandidate(
            contact=contact,
            email=email,
            status=status,
            confidence=1.0 if status == "verified" else None,
            source="prospeo",
        )

    def _headers(self) -> dict[str, str]:
        return {
            "X-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_if_error(data: dict[str, Any]) -> None:
        if data.get("error"):
            code = data.get("error_code") or "UNKNOWN"
            detail = data.get("filter_error") or data.get("message") or data
            raise ProviderHTTPError(f"Prospeo returned {code}: {detail}")


def _map_email_status(status: str | None, email: str | None) -> str:
    normalized = (status or "").lower()
    if normalized == "verified" and email:
        return "verified"
    if normalized in {"risky", "catch_all", "catch-all"} and email:
        return "risky"
    if not email:
        return "not_found"
    return "unknown"


def _source_id(source: str) -> str | None:
    prefix = "prospeo:"
    if not source.startswith(prefix):
        return None
    value = source.removeprefix(prefix)
    return None if value == "search" else value


def _domain_from_website(value: str | None) -> str | None:
    if not value:
        return None
    domain = value.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return domain.split("/", 1)[0] or None
