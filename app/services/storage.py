from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models import PipelineResult
from app.services.reporting import render_report


class RunStorage:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.runs_dir = data_dir / "runs"
        self.db_path = data_dir / "runs.db"

    def ensure(self) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    seed_domain TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    send_enabled INTEGER NOT NULL,
                    companies INTEGER NOT NULL,
                    contacts INTEGER NOT NULL,
                    outreach_emails INTEGER NOT NULL,
                    send_results INTEGER NOT NULL
                )
                """
            )

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def save(self, result: PipelineResult) -> None:
        self.ensure()
        output_dir = result.context.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(output_dir / "run.json", result.context.model_dump(mode="json"))
        self._write_json(
            output_dir / "companies.json",
            [item.model_dump(mode="json") for item in result.companies],
        )
        self._write_json(
            output_dir / "contacts.json",
            [item.model_dump(mode="json") for item in result.contacts],
        )
        self._write_json(
            output_dir / "email_candidates.json",
            [item.model_dump(mode="json") for item in result.email_candidates],
        )
        self._write_outreach_csv(output_dir / "outreach_emails.csv", result)
        self._write_json(
            output_dir / "send_results.json",
            [item.model_dump(mode="json") for item in result.send_results],
        )
        (output_dir / "report.md").write_text(render_report(result), encoding="utf-8")
        self._save_metadata(result)

    def load_artifacts(self, run_id: str) -> dict[str, Any]:
        run_dir = self.run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(run_id)
        artifacts: dict[str, Any] = {}
        for name in ["run", "companies", "contacts", "email_candidates", "send_results"]:
            path = run_dir / f"{name}.json"
            artifacts[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return artifacts

    def export_run(self, run_id: str) -> list[Path]:
        run_dir = self.run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(run_id)
        artifacts = self.load_artifacts(run_id)
        export_json = run_dir / "export.json"
        export_csv = run_dir / "export.csv"
        self._write_json(export_json, artifacts)

        candidates = artifacts.get("email_candidates", [])
        with export_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["name", "title", "company_domain", "email", "status", "source"],
            )
            writer.writeheader()
            for item in candidates:
                contact = item.get("contact", {})
                writer.writerow(
                    {
                        "name": contact.get("full_name"),
                        "title": contact.get("title"),
                        "company_domain": contact.get("company_domain"),
                        "email": item.get("email"),
                        "status": item.get("status"),
                        "source": item.get("source"),
                    }
                )
        return [export_json, export_csv]

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _write_outreach_csv(path: Path, result: PipelineResult) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "to_email",
                    "to_name",
                    "company_domain",
                    "subject",
                    "text_body",
                    "html_body",
                    "personalization_notes",
                ],
            )
            writer.writeheader()
            for email in result.outreach_emails:
                row = email.model_dump(mode="json")
                row["personalization_notes"] = "; ".join(email.personalization_notes)
                writer.writerow(row)

    def _save_metadata(self, result: PipelineResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, seed_domain, started_at, output_dir, dry_run, send_enabled,
                    companies, contacts, outreach_emails, send_results
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.context.run_id,
                    result.context.seed_domain,
                    result.context.started_at.isoformat(),
                    str(result.context.output_dir),
                    int(result.context.dry_run),
                    int(result.context.send_enabled),
                    len(result.companies),
                    len(result.contacts),
                    len(result.outreach_emails),
                    len(result.send_results),
                ),
            )
