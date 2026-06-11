from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from rich.console import Console

from app.clients.base import (
    CompanyDiscoveryClient,
    DecisionMakerClient,
    EmailResolverClient,
    EmailSenderClient,
)
from app.clients.brevo import BrevoClient
from app.clients.eazyreach import EazyreachClient
from app.clients.mock import (
    MockBrevoClient,
    MockDiscoveryClient,
    MockEmailResolverClient,
    MockProspeoClient,
)
from app.clients.ocean import OceanClient
from app.clients.prospeo import ProspeoClient
from app.config import Settings
from app.errors import ConfigurationError
from app.models import (
    EmailCandidate,
    OutreachEmail,
    PipelineResult,
    RunContext,
    SendResult,
    StageResult,
)
from app.services.dedupe import dedupe_contacts, dedupe_email_candidates
from app.services.email_copy import EmailCopyService
from app.services.safety import confirm_send, dry_run_results, show_safety_preview
from app.services.storage import RunStorage
from app.services.validators import is_valid_email

logger = logging.getLogger(__name__)


class UnconfiguredSender:
    async def send_email(self, outreach_email) -> SendResult:  # noqa: ANN001
        raise ConfigurationError("BREVO_API_KEY and BREVO_SENDER_EMAIL are required for --send")


class OutreachPipeline:
    def __init__(
        self,
        *,
        discovery_client: CompanyDiscoveryClient,
        decision_maker_client: DecisionMakerClient,
        email_resolver_client: EmailResolverClient,
        sender_client: EmailSenderClient,
        storage: RunStorage,
        copy_service: EmailCopyService,
        console: Console,
        confirm_callback: Callable[[], str] | None = None,
        show_preview: bool = True,
    ) -> None:
        self.discovery_client = discovery_client
        self.decision_maker_client = decision_maker_client
        self.email_resolver_client = email_resolver_client
        self.sender_client = sender_client
        self.storage = storage
        self.copy_service = copy_service
        self.console = console
        self.confirm_callback = confirm_callback
        self.show_preview = show_preview

    async def run(self, context: RunContext) -> PipelineResult:
        result = PipelineResult(context=context)
        try:
            await self._discover_companies(result)
            await self._discover_contacts(result)
            await self._resolve_emails(result)
            self._dedupe_and_validate(result)
            self._generate_copy(result)
            await self._safety_and_send(result)
            return result
        finally:
            self.storage.save(result)
            await self._close_clients()

    async def _discover_companies(self, result: PipelineResult) -> None:
        errors: list[str] = []
        try:
            result.companies = await self.discovery_client.discover_similar_companies(
                result.context.seed_domain,
                result.context.limit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Company discovery failed")
            errors.append(str(exc))
        result.stages.append(
            StageResult(
                name="discover_companies",
                ok=not errors,
                count=len(result.companies),
                errors=errors,
            )
        )

    async def _discover_contacts(self, result: PipelineResult) -> None:
        errors: list[str] = []
        contacts = []
        per_company_limit = max(1, min(3, result.context.limit))
        for company in result.companies:
            try:
                contacts.extend(
                    await self.decision_maker_client.find_decision_makers(
                        company,
                        per_company_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Decision-maker discovery failed for %s", company.domain)
                errors.append(f"{company.domain}: {exc}")
        result.contacts = contacts[: result.context.limit]
        result.stages.append(
            StageResult(
                name="discover_decision_makers",
                ok=not errors,
                count=len(result.contacts),
                errors=errors,
            )
        )

    async def _resolve_emails(self, result: PipelineResult) -> None:
        errors: list[str] = []
        candidates: list[EmailCandidate] = []
        for contact in result.contacts:
            try:
                candidates.append(await self.email_resolver_client.resolve_email(contact))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Email resolution failed for %s", contact.full_name)
                errors.append(f"{contact.full_name or contact.company_domain}: {exc}")
                candidates.append(
                    EmailCandidate(contact=contact, email=None, status="unknown", source="error")
                )
        result.email_candidates = candidates
        result.stages.append(
            StageResult(name="resolve_emails", ok=not errors, count=len(candidates), errors=errors)
        )

    def _dedupe_and_validate(self, result: PipelineResult) -> None:
        unique_contacts, contact_dupes = dedupe_contacts(result.contacts)
        unique_candidates, email_dupes = dedupe_email_candidates(result.email_candidates)
        invalid_count = sum(
            1
            for candidate in unique_candidates
            if candidate.email is not None and not is_valid_email(candidate.email)
        )
        result.contacts = unique_contacts
        result.email_candidates = [
            candidate
            for candidate in unique_candidates
            if candidate.email is None or is_valid_email(candidate.email)
        ]
        result.duplicates_removed = contact_dupes + email_dupes
        result.skipped_emails = sum(
            1
            for candidate in result.email_candidates
            if candidate.status != "verified" or not candidate.email
        ) + invalid_count
        result.stages.append(
            StageResult(
                name="dedupe_and_validate",
                ok=True,
                count=len(result.email_candidates),
                metadata={
                    "contact_duplicates": contact_dupes,
                    "email_duplicates": email_dupes,
                    "invalid_emails": invalid_count,
                },
            )
        )

    def _generate_copy(self, result: PipelineResult) -> None:
        outreach_emails = []
        errors: list[str] = []
        for candidate in result.email_candidates:
            try:
                outreach_email = self.copy_service.generate(candidate)
                if outreach_email:
                    outreach_emails.append(outreach_email)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Copy generation failed for %s", candidate.email)
                errors.append(f"{candidate.email or candidate.contact.full_name}: {exc}")
        result.outreach_emails = outreach_emails
        result.stages.append(
            StageResult(
                name="generate_outreach_emails",
                ok=not errors,
                count=len(outreach_emails),
                errors=errors,
            )
        )

    async def _safety_and_send(self, result: PipelineResult) -> None:
        if self.show_preview:
            show_safety_preview(result=result, console=self.console)

        if not result.context.send_enabled:
            result.send_results = dry_run_results(result.outreach_emails)
            result.stages.append(
                StageResult(name="dry_run", ok=True, count=len(result.send_results))
            )
            return

        approved = confirm_send(console=self.console, ask=self.confirm_callback)
        if not approved:
            result.context.dry_run = True
            result.context.send_enabled = False
            result.send_results = dry_run_results(result.outreach_emails)
            result.stages.append(
                StageResult(
                    name="send_confirmation",
                    ok=True,
                    count=0,
                    metadata={"approved": False},
                )
            )
            return

        send_results: list[SendResult] = []
        errors: list[str] = []
        for outreach_email in result.outreach_emails:
            email_to_send = _apply_test_recipient(outreach_email, result.context.test_recipient)
            try:
                send_results.append(await self.sender_client.send_email(email_to_send))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Email send failed for %s", email_to_send.to_email)
                errors.append(f"{email_to_send.to_email}: {exc}")
                send_results.append(
                    SendResult(
                        email=email_to_send.to_email,
                        status="failed",
                        provider_message_id=None,
                        error=str(exc),
                    )
                )
        result.send_results = send_results
        result.stages.append(
            StageResult(name="send_emails", ok=not errors, count=len(send_results), errors=errors)
        )

    async def _close_clients(self) -> None:
        for client in {
            self.discovery_client,
            self.decision_maker_client,
            self.email_resolver_client,
            self.sender_client,
        }:
            close = getattr(client, "close", None)
            if close:
                await close()


def create_run_context(
    *,
    seed_domain: str,
    settings: Settings,
    dry_run: bool,
    send_enabled: bool,
    limit: int,
    test_recipient: str | None = None,
) -> RunContext:
    started_at = datetime.now(UTC)
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    safe_domain = seed_domain.replace(".", "-")
    run_id = f"{timestamp}_{safe_domain}"
    output_dir = settings.data_dir / "runs" / run_id
    return RunContext(
        run_id=run_id,
        seed_domain=seed_domain,
        started_at=started_at,
        dry_run=dry_run,
        send_enabled=send_enabled,
        limit=limit,
        output_dir=output_dir,
        test_recipient=test_recipient,
    )


def create_pipeline(
    *,
    settings: Settings,
    mock: bool,
    console: Console,
    confirm_callback: Callable[[], str] | None = None,
    show_preview: bool = True,
) -> OutreachPipeline:
    if mock:
        discovery_client = MockDiscoveryClient()
        people_client = MockProspeoClient()
        resolver_client = MockEmailResolverClient()
        sender_client = MockBrevoClient()
    else:
        if settings.company_discovery_provider == "mock":
            discovery_client = MockDiscoveryClient()
        elif not settings.ocean_api_key:
            raise ConfigurationError("OCEAN_API_KEY is required outside --mock mode")
        else:
            discovery_client = OceanClient(
                api_key=settings.ocean_api_key,
                base_url=settings.ocean_base_url,
                lookalike_endpoint=settings.ocean_lookalike_endpoint,
                lookalike_method=settings.ocean_lookalike_method,
                auth_header=settings.ocean_auth_header,
                auth_prefix=settings.ocean_auth_prefix,
                seed_domain_field=settings.ocean_seed_domain_field,
                limit_field=settings.ocean_limit_field,
                response_companies_path=settings.ocean_response_companies_path,
                company_name_field=settings.ocean_company_name_field,
                company_domain_field=settings.ocean_company_domain_field,
                company_score_field=settings.ocean_company_score_field,
                lookalike_body_template=settings.ocean_lookalike_body_template,
                timeout_seconds=settings.request_timeout_seconds,
                max_retries=settings.max_retries,
            )
        if not settings.prospeo_api_key:
            raise ConfigurationError("PROSPEO_API_KEY is required outside --mock mode")
        people_client = ProspeoClient(
            api_key=settings.prospeo_api_key,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )
        resolver_client = _build_email_resolver(settings, people_client)
        sender_client = _build_sender(settings)

    return OutreachPipeline(
        discovery_client=discovery_client,
        decision_maker_client=people_client,
        email_resolver_client=resolver_client,
        sender_client=sender_client,
        storage=RunStorage(settings.data_dir),
        copy_service=EmailCopyService(),
        console=console,
        confirm_callback=confirm_callback,
        show_preview=show_preview,
    )


def _build_email_resolver(settings: Settings, prospeo_client: ProspeoClient) -> EmailResolverClient:
    if settings.email_provider == "eazyreach" and settings.eazyreach_enabled:
        if settings.eazyreach_api_key:
            return EazyreachClient(
                api_key=settings.eazyreach_api_key,
                timeout_seconds=settings.request_timeout_seconds,
                max_retries=settings.max_retries,
            )
        return prospeo_client
    return prospeo_client


def _build_sender(settings: Settings) -> EmailSenderClient:
    if settings.brevo_api_key and settings.brevo_sender_email:
        return BrevoClient(
            api_key=settings.brevo_api_key,
            sender_email=settings.brevo_sender_email,
            sender_name=settings.brevo_sender_name,
            sandbox=settings.brevo_sandbox,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )
    return UnconfiguredSender()


def _apply_test_recipient(
    outreach_email: OutreachEmail,
    test_recipient: str | None,
) -> OutreachEmail:
    if not test_recipient:
        return outreach_email

    original_name = outreach_email.to_name or "Unknown"
    original_line = (
        "DEMO ROUTING NOTE: Original intended recipient was "
        f"{original_name} <{outreach_email.to_email}>."
    )
    html_note = (
        "<p><strong>Demo routing note:</strong> Original intended recipient was "
        f"{original_name} &lt;{outreach_email.to_email}&gt;.</p>"
    )
    html_body = (
        f"{html_note}\n{outreach_email.html_body}" if outreach_email.html_body else html_note
    )
    return outreach_email.model_copy(
        update={
            "to_email": test_recipient,
            "to_name": "Test Recipient",
            "text_body": f"{original_line}\n\n{outreach_email.text_body}",
            "html_body": html_body,
            "personalization_notes": [
                *outreach_email.personalization_notes,
                f"Demo-routed to {test_recipient}",
            ],
        }
    )
