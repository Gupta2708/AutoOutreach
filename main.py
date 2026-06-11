from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.clients.brevo import BrevoClient
from app.clients.ocean import OceanClient, OceanDebugResult, debug_result_to_dict
from app.clients.prospeo import ProspeoClient
from app.config import Settings
from app.errors import ConfigurationError, PipelineError, ValidationError
from app.logging import configure_logging
from app.models import Company, OutreachEmail
from app.pipeline import create_pipeline, create_run_context
from app.services.reporting import print_run_summary
from app.services.storage import RunStorage
from app.services.validators import is_valid_email, normalize_domain

app = typer.Typer(help="Automated cold outreach pipeline CLI.")
console = Console()


@app.command("validate-env")
def validate_env() -> None:
    """Validate local configuration and API key readiness."""
    configure_logging()
    settings = Settings()
    console.print("[bold]Environment[/bold]")
    console.print(f"Data directory: {settings.data_dir}")
    console.print(f"Company discovery provider: {settings.company_discovery_provider}")
    console.print(f"Email provider: {settings.email_provider}")
    console.print(f"Eazyreach enabled: {settings.eazyreach_enabled}")
    console.print(f"Brevo sandbox: {settings.brevo_sandbox}")
    console.print(f"Test recipient: {settings.test_recipient or '[not set]'}")
    console.print(f"Default limit: {settings.default_limit}")

    missing = settings.missing_real_mode_keys()
    if settings.ocean_endpoint_missing():
        console.print(
            "[yellow]Ocean lookalike endpoint is not configured. Open Ocean.io API docs "
            "and set OCEAN_LOOKALIKE_ENDPOINT.[/yellow]"
        )
    if missing:
        console.print("[yellow]Real mode is missing:[/yellow] " + ", ".join(missing))
        console.print("[green]Mock mode is ready and does not require API keys.[/green]")
        raise typer.Exit(code=1)

    console.print("[green]Real mode configuration looks complete.[/green]")


@app.command()
def run(
    domain: str = typer.Option(..., "--domain", help="Seed company domain, e.g. example.com."),
    mock: bool = typer.Option(False, "--mock", help="Use offline mock providers."),
    send: bool = typer.Option(False, "--send", help="Allow sending after SEND confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Force dry-run behavior."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Cap contacts/emails."),
    test_recipient: str | None = typer.Option(
        None,
        "--test-recipient",
        help=(
            "Send all approved emails to this address while preserving original recipient in body."
        ),
    ),
) -> None:
    """Run the outreach pipeline from a seed domain."""
    configure_logging()
    settings = Settings()

    try:
        seed_domain = normalize_domain(domain)
        effective_limit = limit or settings.default_limit
        effective_test_recipient = test_recipient or settings.test_recipient
        if effective_test_recipient and not is_valid_email(effective_test_recipient):
            raise ValidationError(f"Invalid --test-recipient: {effective_test_recipient}")
        send_enabled = send and not dry_run
        context = create_run_context(
            seed_domain=seed_domain,
            settings=settings,
            dry_run=not send_enabled,
            send_enabled=send_enabled,
            limit=effective_limit,
            test_recipient=effective_test_recipient,
        )
        pipeline = create_pipeline(settings=settings, mock=mock, console=console)
        result = asyncio.run(pipeline.run(context))
    except (ConfigurationError, PipelineError, ValidationError) as exc:
        console.print(f"[red]Pipeline failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    print_run_summary(result, console)


@app.command()
def resume(run_id: str = typer.Option(..., "--run-id", help="Existing run id.")) -> None:
    """Inspect a saved run and show what was completed."""
    settings = Settings()
    storage = RunStorage(settings.data_dir)
    try:
        artifacts = storage.load_artifacts(run_id)
    except FileNotFoundError as exc:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Run:[/bold] {run_id}")
    console.print(f"Companies: {len(artifacts.get('companies', []))}")
    console.print(f"Contacts: {len(artifacts.get('contacts', []))}")
    console.print(f"Email candidates: {len(artifacts.get('email_candidates', []))}")
    console.print(f"Send results: {len(artifacts.get('send_results', []))}")
    console.print(f"Report: {storage.run_dir(run_id) / 'report.md'}")


@app.command()
def export(run_id: str = typer.Option(..., "--run-id", help="Existing run id.")) -> None:
    """Create consolidated CSV and JSON export files for a run."""
    settings = Settings()
    storage = RunStorage(settings.data_dir)
    try:
        paths = storage.export_run(run_id)
    except FileNotFoundError as exc:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(code=1) from exc

    console.print("[green]Exported:[/green]")
    for path in paths:
        console.print(Path(path))


@app.command("test-provider")
def test_provider(
    provider: str = typer.Argument(..., help="Provider to test: ocean, prospeo, or brevo."),
    domain: str | None = typer.Option(
        None,
        "--domain",
        help="Seed/company domain for provider test.",
    ),
    debug: bool = typer.Option(False, "--debug", help="Print sanitized request/response details."),
    sandbox: bool = typer.Option(False, "--sandbox", help="Force Brevo sandbox drop mode."),
    to: str | None = typer.Option(None, "--to", help="Recipient for Brevo provider test."),
) -> None:
    """Smoke-test one configured provider without running the full pipeline."""
    configure_logging()
    settings = Settings()
    provider_name = provider.strip().lower()
    try:
        if provider_name == "ocean":
            if not domain:
                raise ValidationError("--domain is required for Ocean provider tests")
            asyncio.run(_test_ocean(settings, normalize_domain(domain), debug=debug))
        elif provider_name == "prospeo":
            if not domain:
                raise ValidationError("--domain is required for Prospeo provider tests")
            asyncio.run(_test_prospeo(settings, normalize_domain(domain)))
        elif provider_name == "brevo":
            recipient = (
                to
                or settings.test_recipient
                or (settings.brevo_sender_email if sandbox else None)
            )
            if not recipient:
                raise ValidationError("Use --to or set TEST_RECIPIENT for Brevo provider tests")
            if not is_valid_email(recipient):
                raise ValidationError(f"Invalid Brevo test recipient: {recipient}")
            asyncio.run(_test_brevo(settings, recipient, force_sandbox=sandbox))
        else:
            raise ValidationError("Provider must be one of: ocean, prospeo, brevo")
    except (ConfigurationError, PipelineError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Provider test failed", border_style="red"))
        raise typer.Exit(code=1) from exc


@app.command("probe-ocean")
def probe_ocean(
    method: str = typer.Option("POST", "--method", help="HTTP method from Ocean docs."),
    endpoint: str = typer.Option(..., "--endpoint", help="Endpoint path copied from Ocean docs."),
    domain: str = typer.Option(..., "--domain", help="Seed company domain."),
    limit: int = typer.Option(5, "--limit", min=1, help="Probe result limit."),
) -> None:
    """Call a raw Ocean endpoint, print sanitized debug details, and save the response."""
    configure_logging()
    settings = Settings()
    try:
        result = asyncio.run(
            _probe_ocean(
                settings=settings,
                method=method,
                endpoint=endpoint,
                domain=normalize_domain(domain),
                limit=limit,
            )
        )
    except (ConfigurationError, PipelineError, ValidationError) as exc:
        console.print(Panel(str(exc), title="Ocean probe failed", border_style="red"))
        raise typer.Exit(code=1) from exc

    _print_ocean_debug(result)
    path = _save_ocean_probe(settings, result)
    console.print(f"[green]Saved response:[/green] {path}")


async def _test_ocean(settings: Settings, domain: str, *, debug: bool) -> None:
    if not settings.ocean_api_key:
        raise ConfigurationError("OCEAN_API_KEY is required")
    if not settings.ocean_lookalike_endpoint:
        raise ConfigurationError(
            "Ocean lookalike endpoint is not configured. Open Ocean.io API docs and set "
            "OCEAN_LOOKALIKE_ENDPOINT."
        )
    client = _build_ocean_client(settings)
    try:
        if debug:
            result = await client.raw_request(
                method=settings.ocean_lookalike_method,
                endpoint=settings.ocean_lookalike_endpoint,
                seed_domain=domain,
                limit=5,
            )
            _print_ocean_debug(result)
            if result.status_code >= 400:
                raise PipelineError(f"Ocean returned HTTP {result.status_code}")
            data = json.loads(result.response_text) if result.response_text else {}
            companies = client.parse_companies(data, limit=5)
        else:
            companies = await client.discover_similar_companies(domain, limit=5)
    finally:
        await client.close()

    table = Table(title="Ocean.io Similar Companies")
    table.add_column("Name")
    table.add_column("Domain")
    table.add_column("Score")
    for company in companies:
        table.add_row(company.name or "", company.domain, _format_company_score(company))
    console.print(table)


async def _probe_ocean(
    *,
    settings: Settings,
    method: str,
    endpoint: str,
    domain: str,
    limit: int,
):
    if not settings.ocean_api_key:
        raise ConfigurationError("OCEAN_API_KEY is required")
    client = _build_ocean_client(settings)
    try:
        return await client.raw_request(
            method=method,
            endpoint=endpoint,
            seed_domain=domain,
            limit=limit,
        )
    finally:
        await client.close()


def _build_ocean_client(settings: Settings) -> OceanClient:
    return OceanClient(
        api_key=settings.ocean_api_key or "",
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


def _print_ocean_debug(result: OceanDebugResult) -> None:
    console.print("[bold]Ocean Debug[/bold]")
    console.print(f"HTTP method: {result.method}")
    console.print(f"Final URL: {result.url}")
    console.print("Request body:")
    console.print_json(json.dumps(result.request_body))
    console.print("Sanitized headers:")
    console.print_json(json.dumps(result.headers))
    console.print(f"Status code: {result.status_code}")
    console.print("Response body:")
    console.print(result.response_text or "[empty]")


def _save_ocean_probe(settings: Settings, result: OceanDebugResult) -> Path:
    debug_dir = settings.data_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = debug_dir / f"ocean_probe_{timestamp}.json"
    path.write_text(json.dumps(debug_result_to_dict(result), indent=2), encoding="utf-8")
    return path


def _format_company_score(company: Company) -> str:
    if company.similarity_score_label:
        return company.similarity_score_label
    if company.similarity_score is None:
        return ""
    return f"{company.similarity_score:g}"


async def _test_prospeo(settings: Settings, domain: str) -> None:
    if not settings.prospeo_api_key:
        raise ConfigurationError("PROSPEO_API_KEY is required")
    client = ProspeoClient(
        api_key=settings.prospeo_api_key,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
    )
    try:
        contacts = await client.find_decision_makers(
            Company(name=None, domain=domain, source="provider-test"),
            limit=5,
        )
        candidates = []
        for contact in contacts[:1]:
            candidates.append(await client.resolve_email(contact))
    finally:
        await client.close()

    table = Table(title="Prospeo Decision-Makers and Emails")
    table.add_column("Name")
    table.add_column("Title")
    table.add_column("Email")
    table.add_column("Status")
    for candidate in candidates:
        contact = candidate.contact
        table.add_row(
            contact.full_name or "",
            contact.title or "",
            candidate.email or "",
            candidate.status,
        )
    console.print(table)


async def _test_brevo(settings: Settings, recipient: str, *, force_sandbox: bool) -> None:
    if not settings.brevo_api_key or not settings.brevo_sender_email:
        raise ConfigurationError("BREVO_API_KEY and BREVO_SENDER_EMAIL are required")
    client = BrevoClient(
        api_key=settings.brevo_api_key,
        sender_email=settings.brevo_sender_email,
        sender_name=settings.brevo_sender_name,
        sandbox=force_sandbox or settings.brevo_sandbox,
        timeout_seconds=settings.request_timeout_seconds,
        max_retries=settings.max_retries,
    )
    try:
        result = await client.send_email(
            OutreachEmail(
                to_email=recipient,
                to_name="Provider Test",
                company_domain="provider-test.local",
                subject="AutoOutreach Brevo provider test",
                text_body="This is a Brevo provider smoke test from AutoOutreach.",
                html_body="<p>This is a Brevo provider smoke test from AutoOutreach.</p>",
                personalization_notes=["Provider smoke test"],
            )
        )
    finally:
        await client.close()
    console.print(
        f"[green]Brevo result:[/green] {result.status} {result.provider_message_id or ''}"
    )


if __name__ == "__main__":
    app()
