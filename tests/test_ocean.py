from __future__ import annotations

import asyncio

import pytest

from app.clients.ocean import OceanClient, get_nested_value, sanitize_headers
from app.errors import ConfigurationError


def make_client(**overrides) -> OceanClient:
    config = {
        "api_key": "sk_live_secret",
        "base_url": "https://api.ocean.io",
        "lookalike_endpoint": "/lookalikes",
        "lookalike_method": "POST",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "seed_domain_field": "domain",
        "limit_field": "limit",
        "response_companies_path": None,
        "company_name_field": "name",
        "company_domain_field": "domain",
        "company_score_field": "similarity_score",
        "lookalike_body_template": None,
        "timeout_seconds": 1,
        "max_retries": 1,
    }
    config.update(overrides)
    return OceanClient(**config)


def test_get_nested_value() -> None:
    data = {"data": {"results": [{"domain": "apollo.io"}]}}
    assert get_nested_value(data, "data.results.0.domain") == "apollo.io"
    assert get_nested_value(data, "data.missing") is None


def test_ocean_response_parsing_with_companies() -> None:
    client = make_client()
    companies = client.parse_companies(
        {"companies": [{"name": "Apollo", "domain": "apollo.io", "similarity_score": 0.91}]},
        limit=5,
    )
    assert companies[0].name == "Apollo"
    assert companies[0].domain == "apollo.io"
    assert companies[0].similarity_score == 0.91


def test_ocean_response_parsing_with_data_results() -> None:
    client = make_client(response_companies_path="data.results")
    companies = client.parse_companies(
        {"data": {"results": [{"name": "Oliv", "domain": "oliv.ai"}]}},
        limit=5,
    )
    assert len(companies) == 1
    assert companies[0].domain == "oliv.ai"


def test_ocean_missing_endpoint_clean_error() -> None:
    client = make_client(lookalike_endpoint=None)
    with pytest.raises(ConfigurationError, match="Ocean lookalike endpoint is not configured"):
        asyncio.run(client.discover_similar_companies("apollo.io", 3))
    asyncio.run(client.close())


def test_no_api_key_leakage_in_debug_headers() -> None:
    headers = sanitize_headers(
        {
            "Authorization": "Bearer sk_live_secret_value",
            "Content-Type": "application/json",
        }
    )
    assert "sk_live_secret_value" not in str(headers)
    assert headers["Authorization"].startswith("Bearer sk_l")
    assert headers["Authorization"].endswith("alue")


def test_ocean_body_template_supports_plain_json_braces() -> None:
    client = make_client(
        lookalike_body_template=(
            '{"size":{limit},"companiesFilters":{"lookalikeDomains":["{domain}"]}}'
        )
    )
    assert client.build_body(seed_domain="apollo.io", limit=3) == {
        "size": 3,
        "companiesFilters": {"lookalikeDomains": ["apollo.io"]},
    }


def test_ocean_response_parsing_with_nested_company_shape() -> None:
    client = make_client(
        company_name_field="company.name",
        company_domain_field="company.domain",
        company_score_field="relevance",
    )
    companies = client.parse_companies(
        {"companies": [{"company": {"name": "Lusha", "domain": "lusha.com"}, "relevance": "A"}]},
        limit=5,
    )
    assert companies[0].name == "Lusha"
    assert companies[0].domain == "lusha.com"
