from __future__ import annotations

from app.clients.base import CompanyDiscoveryClient
from app.models import Company


async def discover_companies(
    client: CompanyDiscoveryClient,
    seed_domain: str,
    limit: int,
) -> list[Company]:
    return await client.discover_similar_companies(seed_domain, limit)
