from __future__ import annotations

import asyncio
import io

from rich.console import Console

from app.config import Settings
from app.pipeline import create_pipeline, create_run_context


def test_mock_pipeline_end_to_end_saves_artifacts(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "data", default_limit=10)
    console = Console(file=io.StringIO())
    context = create_run_context(
        seed_domain="example.com",
        settings=settings,
        dry_run=True,
        send_enabled=False,
        limit=10,
    )
    pipeline = create_pipeline(settings=settings, mock=True, console=console, show_preview=False)

    result = asyncio.run(pipeline.run(context))

    assert len(result.companies) == 5
    assert result.outreach_emails
    assert all(send.status == "dry_run" for send in result.send_results)
    assert (context.output_dir / "run.json").exists()
    assert (context.output_dir / "report.md").exists()


def test_send_mode_decline_saves_as_dry_run(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "data", default_limit=5)
    console = Console(file=io.StringIO())
    context = create_run_context(
        seed_domain="example.com",
        settings=settings,
        dry_run=False,
        send_enabled=True,
        limit=5,
    )
    pipeline = create_pipeline(
        settings=settings,
        mock=True,
        console=console,
        confirm_callback=lambda: "NO",
        show_preview=False,
    )

    result = asyncio.run(pipeline.run(context))

    assert result.context.dry_run is True
    assert result.context.send_enabled is False
    assert result.send_results
    assert all(send.status == "dry_run" for send in result.send_results)


def test_mock_send_mode_includes_demo_failure(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "data", default_limit=5)
    console = Console(file=io.StringIO())
    context = create_run_context(
        seed_domain="example.com",
        settings=settings,
        dry_run=False,
        send_enabled=True,
        limit=5,
    )
    pipeline = create_pipeline(
        settings=settings,
        mock=True,
        console=console,
        confirm_callback=lambda: "SEND",
        show_preview=False,
    )

    result = asyncio.run(pipeline.run(context))

    assert any(send.status == "sent" for send in result.send_results)
    assert any(send.status == "failed" for send in result.send_results)


def test_test_recipient_routes_approved_sends_away_from_prospects(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "data", default_limit=5)
    console = Console(file=io.StringIO())
    context = create_run_context(
        seed_domain="example.com",
        settings=settings,
        dry_run=False,
        send_enabled=True,
        limit=5,
        test_recipient="demo@example.com",
    )
    pipeline = create_pipeline(
        settings=settings,
        mock=True,
        console=console,
        confirm_callback=lambda: "SEND",
        show_preview=False,
    )

    result = asyncio.run(pipeline.run(context))

    assert result.send_results
    assert {send.email for send in result.send_results} == {"demo@example.com"}
