from __future__ import annotations

from rich.console import Console

from app.models import PipelineResult


def render_report(result: PipelineResult) -> str:
    failed = [item for item in result.send_results if item.status == "failed"]
    sent = [item for item in result.send_results if item.status == "sent"]
    dry_run = [item for item in result.send_results if item.status == "dry_run"]

    lines = [
        f"# Outreach Run {result.context.run_id}",
        "",
        f"- Seed domain: `{result.context.seed_domain}`",
        f"- Dry-run: `{result.context.dry_run}`",
        f"- Send enabled: `{result.context.send_enabled}`",
        f"- Limit: `{result.context.limit}`",
        f"- Companies discovered: `{len(result.companies)}`",
        f"- Contacts processed: `{len(result.contacts)}`",
        f"- Verified emails: `{result.verified_emails}`",
        f"- Skipped emails: `{result.skipped_emails}`",
        f"- Duplicates removed: `{result.duplicates_removed}`",
        f"- Sent: `{len(sent)}`",
        f"- Dry-run results: `{len(dry_run)}`",
        f"- Failed sends: `{len(failed)}`",
        "",
        "## Stages",
        "",
    ]
    for stage in result.stages:
        marker = "ok" if stage.ok else "partial"
        lines.append(f"- {stage.name}: {marker}, count={stage.count}")
        for error in stage.errors:
            lines.append(f"  - error: {error}")
    return "\n".join(lines) + "\n"


def print_run_summary(result: PipelineResult, console: Console) -> None:
    console.print("[bold green]Run complete[/bold green]")
    console.print(f"Run id: {result.context.run_id}")
    console.print(f"Output: {result.context.output_dir}")
    console.print(f"Companies: {len(result.companies)}")
    console.print(f"Contacts: {len(result.contacts)}")
    console.print(f"Outreach emails: {len(result.outreach_emails)}")
    console.print(f"Send results: {len(result.send_results)}")
