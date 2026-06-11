from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.models import Company, Contact, EmailCandidate, OutreachEmail, SendResult

logger = logging.getLogger(__name__)


class CompanyDiscoveryClient(Protocol):
    async def discover_similar_companies(self, seed_domain: str, limit: int) -> list[Company]:
        ...


class DecisionMakerClient(Protocol):
    async def find_decision_makers(self, company: Company, limit: int) -> list[Contact]:
        ...


class EmailResolverClient(Protocol):
    async def resolve_email(self, contact: Contact) -> EmailCandidate:
        ...


class EmailSenderClient(Protocol):
    async def send_email(self, outreach_email: OutreachEmail) -> SendResult:
        ...


class BaseAPIClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((ProviderRateLimitError, ProviderTimeoutError)),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self._client.request(
                        method,
                        path,
                        headers=headers,
                        json=json,
                        params=params,
                    )
                except httpx.TimeoutException as exc:
                    raise ProviderTimeoutError("Provider request timed out") from exc
                except httpx.ConnectError as exc:
                    raise ProviderConnectionError(f"Could not connect to provider: {exc}") from exc

                if response.status_code in {401, 403}:
                    raise ProviderAuthError("Provider authentication failed")
                if response.status_code == 429:
                    raise ProviderRateLimitError("Provider rate limit reached")
                if response.is_error:
                    body = response.text.strip()
                    detail = f"{response.status_code} {response.reason_phrase} for {response.url}"
                    if body:
                        detail = f"{detail}: {body[:500]}"
                    raise ProviderHTTPError(detail)
                if not response.content:
                    return {}
                data = response.json()
                if isinstance(data, dict):
                    return data
                return {"data": data}

        return {}
