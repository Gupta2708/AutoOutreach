from __future__ import annotations

import httpx

from app.clients.prospeo import ProspeoClient
from app.models import Company, Contact


def make_client(handler) -> ProspeoClient:
    client = ProspeoClient(api_key="secret", timeout_seconds=1, max_retries=1)
    client._client = httpx.AsyncClient(  # noqa: SLF001
        base_url="https://api.prospeo.io",
        transport=httpx.MockTransport(handler),
    )
    return client


async def close_client(client: ProspeoClient) -> None:
    await client.close()


def test_prospeo_search_person_parses_results() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/search-person"
            return httpx.Response(
                200,
                json={
                    "error": False,
                    "results": [
                        {
                            "person": {
                                "person_id": "abc123",
                                "first_name": "Maya",
                                "last_name": "Chen",
                                "full_name": "Maya Chen",
                                "current_job_title": "VP Sales",
                                "linkedin_url": "https://linkedin.com/in/maya",
                            },
                            "company": {
                                "name": "Apollo",
                                "domain": "apollo.io",
                            },
                        }
                    ],
                },
            )

        client = make_client(handler)
        try:
            contacts = await client.find_decision_makers(
                Company(name="Apollo", domain="apollo.io", source="test"),
                limit=5,
            )
        finally:
            await close_client(client)
        assert contacts[0].full_name == "Maya Chen"
        assert contacts[0].company_domain == "apollo.io"
        assert contacts[0].source == "prospeo:abc123"

    import asyncio

    asyncio.run(run())


def test_prospeo_enrich_person_parses_verified_email() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/enrich-person"
            return httpx.Response(
                200,
                json={
                    "error": False,
                    "person": {
                        "email": {
                            "status": "VERIFIED",
                            "email": "maya@apollo.io",
                        }
                    },
                },
            )

        client = make_client(handler)
        try:
            candidate = await client.resolve_email(
                Contact(
                    first_name="Maya",
                    last_name="Chen",
                    full_name="Maya Chen",
                    company_domain="apollo.io",
                    source="prospeo:abc123",
                )
            )
        finally:
            await close_client(client)
        assert candidate.email == "maya@apollo.io"
        assert candidate.status == "verified"

    import asyncio

    asyncio.run(run())
