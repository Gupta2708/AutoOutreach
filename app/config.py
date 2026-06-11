from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ocean_api_key: str | None = None
    ocean_base_url: str = "https://api.ocean.io"
    ocean_lookalike_endpoint: str | None = "/v3/search/companies"
    ocean_lookalike_method: str = "POST"
    ocean_auth_header: str = "x-api-token"
    ocean_auth_prefix: str = ""
    ocean_seed_domain_field: str = "domain"
    ocean_limit_field: str = "limit"
    ocean_response_companies_path: str | None = "companies"
    ocean_company_name_field: str = "company.name"
    ocean_company_domain_field: str = "company.domain"
    ocean_company_score_field: str = "relevance"
    ocean_lookalike_body_template: str | None = (
        '{"size":{limit},"companiesFilters":{"lookalikeDomains":["{domain}"]}}'
    )
    company_discovery_provider: Literal["ocean", "mock"] = "ocean"
    prospeo_api_key: str | None = None
    eazyreach_api_key: str | None = None
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "AutoOutreach"
    email_provider: Literal["prospeo", "eazyreach"] = "prospeo"
    eazyreach_enabled: bool = False
    brevo_sandbox: bool = True
    test_recipient: str | None = None
    default_limit: int = Field(default=10, ge=1, le=100)
    request_timeout_seconds: float = Field(default=30, gt=0)
    max_retries: int = Field(default=3, ge=1, le=10)
    data_dir: Path = Path("data")

    def missing_real_mode_keys(self) -> list[str]:
        missing: list[str] = []
        required = {
            "PROSPEO_API_KEY": self.prospeo_api_key,
            "BREVO_API_KEY": self.brevo_api_key,
            "BREVO_SENDER_EMAIL": self.brevo_sender_email,
        }
        if self.company_discovery_provider == "ocean":
            required["OCEAN_API_KEY"] = self.ocean_api_key
        if self.email_provider == "eazyreach" and self.eazyreach_enabled:
            required["EAZYREACH_API_KEY"] = self.eazyreach_api_key

        for name, value in required.items():
            if not value:
                missing.append(name)
        return missing

    def ocean_endpoint_missing(self) -> bool:
        return self.company_discovery_provider == "ocean" and not self.ocean_lookalike_endpoint
