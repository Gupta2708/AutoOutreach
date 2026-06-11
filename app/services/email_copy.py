from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models import EmailCandidate, OutreachEmail


class EmailCopyService:
    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or Path(__file__).resolve().parents[1] / "templates"
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, candidate: EmailCandidate) -> OutreachEmail | None:
        if candidate.status != "verified" or not candidate.email:
            return None

        contact = candidate.contact
        to_name = contact.full_name or "there"
        company = contact.company_name or contact.company_domain
        subject = self.subject_for(candidate)
        notes = [f"Referenced {company}"]
        if contact.title:
            notes.append(f"Referenced role: {contact.title}")

        context = {
            "to_name": to_name,
            "first_name": contact.first_name or to_name,
            "title": contact.title,
            "company": company,
            "company_domain": contact.company_domain,
        }
        text_body = self.env.get_template("outreach_email.txt.j2").render(**context)
        html_body = self.env.get_template("outreach_email.html.j2").render(**context)
        return OutreachEmail(
            to_email=candidate.email,
            to_name=to_name,
            company_domain=contact.company_domain,
            subject=subject,
            text_body=text_body.strip(),
            html_body=html_body.strip(),
            personalization_notes=notes,
        )

    @staticmethod
    def subject_for(candidate: EmailCandidate) -> str:
        contact = candidate.contact
        company = contact.company_name or contact.company_domain
        if contact.title:
            return f"Quick idea for {company}'s {contact.title.lower()} team"
        return f"Quick idea for {company}"
