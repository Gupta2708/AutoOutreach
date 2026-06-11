from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.errors import (
    ConfigurationError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from app.models import Company

logger = logging.getLogger(__name__)

COMMON_COMPANY_PATHS = [
    "companies",
    "data",
    "data.companies",
    "data.results",
    "results",
    "items",
    "records",
]


@dataclass(frozen=True)
class OceanDebugResult:
    method: str
    url: str
    request_body: dict[str, Any] | list[Any] | None
    headers: dict[str, str]
    status_code: int
    response_text: str


class OceanClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        lookalike_endpoint: str | None,
        lookalike_method: str,
        auth_header: str,
        auth_prefix: str,
        seed_domain_field: str,
        limit_field: str,
        response_companies_path: str | None,
        company_name_field: str,
        company_domain_field: str,
        company_score_field: str,
        lookalike_body_template: str | None,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.lookalike_endpoint = lookalike_endpoint.strip() if lookalike_endpoint else None
        self.lookalike_method = lookalike_method.upper()
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix
        self.seed_domain_field = seed_domain_field
        self.limit_field = limit_field
        self.response_companies_path = (
            response_companies_path.strip() if response_companies_path else None
        )
        self.company_name_field = company_name_field
        self.company_domain_field = company_domain_field
        self.company_score_field = company_score_field
        self.lookalike_body_template = (
            lookalike_body_template.strip() if lookalike_body_template else None
        )
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def discover_similar_companies(self, seed_domain: str, limit: int) -> list[Company]:
        if not self.lookalike_endpoint:
            raise ConfigurationError(
                "Ocean lookalike endpoint is not configured. Open Ocean.io API docs and set "
                "OCEAN_LOOKALIKE_ENDPOINT."
            )

        debug = await self.raw_request(
            method=self.lookalike_method,
            endpoint=self.lookalike_endpoint,
            seed_domain=seed_domain,
            limit=limit,
        )
        if debug.status_code >= 400:
            raise ProviderHTTPError(
                f"Ocean returned {debug.status_code} for {debug.method} {debug.url}: "
                f"{debug.response_text[:500]}"
            )

        try:
            data = json.loads(debug.response_text) if debug.response_text else {}
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError("Ocean response was not valid JSON") from exc
        return self.parse_companies(data, limit)

    async def raw_request(
        self,
        *,
        method: str,
        endpoint: str,
        seed_domain: str,
        limit: int,
    ) -> OceanDebugResult:
        body = self.build_body(seed_domain=seed_domain, limit=limit)
        headers = self.build_headers()
        normalized_method = method.upper()
        normalized_endpoint = _normalize_path(endpoint)
        try:
            if normalized_method == "GET":
                response = await self._client.request(
                    normalized_method,
                    normalized_endpoint,
                    headers=headers,
                    params=body if isinstance(body, dict) else None,
                )
            else:
                response = await self._client.request(
                    normalized_method,
                    normalized_endpoint,
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Ocean request timed out") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError(f"Could not connect to Ocean: {exc}") from exc

        return OceanDebugResult(
            method=normalized_method,
            url=str(response.request.url),
            request_body=body,
            headers=sanitize_headers(headers),
            status_code=response.status_code,
            response_text=response.text,
        )

    def build_body(self, *, seed_domain: str, limit: int) -> dict[str, Any] | list[Any]:
        if self.lookalike_body_template:
            rendered = self.lookalike_body_template.replace("{domain}", seed_domain).replace(
                "{limit}", str(limit)
            )
            try:
                body = json.loads(rendered)
            except json.JSONDecodeError as exc:
                raise ConfigurationError("OCEAN_LOOKALIKE_BODY_TEMPLATE is not valid JSON") from exc
            if not isinstance(body, dict | list):
                raise ConfigurationError(
                    "OCEAN_LOOKALIKE_BODY_TEMPLATE must render to JSON object/list"
                )
            return body
        return {
            self.seed_domain_field: seed_domain,
            self.limit_field: limit,
        }

    def build_headers(self) -> dict[str, str]:
        value = self.api_key if not self.auth_prefix else f"{self.auth_prefix} {self.api_key}"
        return {
            self.auth_header: value,
            "Content-Type": "application/json",
        }

    def parse_companies(self, data: dict[str, Any], limit: int) -> list[Company]:
        rows = self._company_rows(data)
        companies: list[Company] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            domain = get_nested_value(row, self.company_domain_field)
            if not domain:
                logger.warning("Skipping Ocean company without domain: %s", row)
                continue
            score = get_nested_value(row, self.company_score_field)
            companies.append(
                Company(
                    name=_as_optional_str(get_nested_value(row, self.company_name_field)),
                    domain=str(domain),
                    source="ocean",
                    similarity_score=_as_optional_float(score),
                    similarity_score_label=_as_optional_str(score),
                )
            )
            if len(companies) >= limit:
                break
        return companies

    def _company_rows(self, data: dict[str, Any]) -> list[Any]:
        paths = (
            [self.response_companies_path]
            if self.response_companies_path
            else COMMON_COMPANY_PATHS
        )
        for path in paths:
            if not path:
                continue
            value = get_nested_value(data, path)
            if isinstance(value, list):
                return value
        return []


def get_nested_value(data: Any, path: str | None) -> Any:
    if path is None or path == "":
        return data
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
        if current is None:
            return None
    return current


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if (
            lower in {"authorization", "x-api-token", "api-key"}
            or "key" in lower
            or "token" in lower
        ):
            sanitized[key] = _mask_secret(value)
        else:
            sanitized[key] = value
    return sanitized


def debug_result_to_dict(result: OceanDebugResult) -> dict[str, Any]:
    return {
        "method": result.method,
        "url": result.url,
        "request_body": result.request_body,
        "headers": result.headers,
        "status_code": result.status_code,
        "response_text": result.response_text,
    }


def _normalize_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _mask_secret(value: str) -> str:
    if not value:
        return "[empty]"
    parts = value.split(" ", 1)
    if len(parts) == 2:
        return f"{parts[0]} {_mask_token(parts[1])}"
    return _mask_token(value)


def _mask_token(token: str) -> str:
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def _as_optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
