from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from app.models import OutreachEmail, PipelineResult, SendResult


def show_safety_preview(
    *,
    result: PipelineResult,
    console: Console,
) -> None:
    table = Table(title="Safety Preview")
    table.add_column("Name")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Email")
    table.add_column("Subject")

    by_email = {email.to_email.lower(): email for email in result.outreach_emails}
    for candidate in result.email_candidates:
        if not candidate.email:
            continue
        outreach_email = by_email.get(candidate.email.lower())
        if not outreach_email:
            continue
        contact = candidate.contact
        table.add_row(
            contact.full_name or "",
            contact.title or "",
            contact.company_name or contact.company_domain,
            candidate.email,
            outreach_email.subject,
        )

    console.print(table)
    console.print(f"Total companies: {len(result.companies)}")
    console.print(f"Contacts: {len(result.contacts)}")
    console.print(f"Verified emails: {result.verified_emails}")
    console.print(f"Skipped emails: {result.skipped_emails}")
    console.print(f"Duplicates removed: {result.duplicates_removed}")


def confirm_send(
    *,
    console: Console,
    ask: Callable[[], str] | None = None,
) -> bool:
    if ask is None:
        def ask_prompt() -> str:
            return Prompt.ask("Send these emails? Type SEND to continue")

        ask = ask_prompt
    answer = ask()
    if answer == "SEND":
        return True
    console.print("[yellow]Sending skipped. Saved as dry-run.[/yellow]")
    return False


def dry_run_results(outreach_emails: list[OutreachEmail]) -> list[SendResult]:
    return [
        SendResult(email=email.to_email, status="dry_run", provider_message_id=None, error=None)
        for email in outreach_emails
    ]
