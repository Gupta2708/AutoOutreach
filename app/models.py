from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EmailStatus = Literal["verified", "risky", "not_found", "unknown"]
SendStatus = Literal["sent", "skipped", "failed", "dry_run"]


class AppModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Company(AppModel):
    name: str | None = None
    domain: str
    source: str
    similarity_score: float | None = None
    similarity_score_label: str | None = None


class Contact(AppModel):
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    title: str | None = None
    company_name: str | None = None
    company_domain: str
    linkedin_url: str | None = None
    source: str


class EmailCandidate(AppModel):
    contact: Contact
    email: str | None = None
    status: EmailStatus = "unknown"
    confidence: float | None = None
    source: str


class OutreachEmail(AppModel):
    to_email: str
    to_name: str | None = None
    company_domain: str
    subject: str
    text_body: str
    html_body: str | None = None
    personalization_notes: list[str] = Field(default_factory=list)


class SendResult(AppModel):
    email: str
    status: SendStatus
    provider_message_id: str | None = None
    error: str | None = None


class RunContext(AppModel):
    run_id: str
    seed_domain: str
    started_at: datetime
    dry_run: bool
    send_enabled: bool
    limit: int
    output_dir: Path
    test_recipient: str | None = None


class StageResult(AppModel):
    name: str
    ok: bool
    count: int = 0
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineResult(AppModel):
    context: RunContext
    companies: list[Company] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    email_candidates: list[EmailCandidate] = Field(default_factory=list)
    outreach_emails: list[OutreachEmail] = Field(default_factory=list)
    send_results: list[SendResult] = Field(default_factory=list)
    stages: list[StageResult] = Field(default_factory=list)
    duplicates_removed: int = 0
    skipped_emails: int = 0

    @property
    def verified_emails(self) -> int:
        return sum(1 for candidate in self.email_candidates if candidate.status == "verified")
