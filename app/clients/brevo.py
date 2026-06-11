from __future__ import annotations

import httpx

from app.clients.base import BaseAPIClient
from app.errors import EmailSendError
from app.models import OutreachEmail, SendResult


class BrevoClient(BaseAPIClient):
    def __init__(
        self,
        *,
        api_key: str,
        sender_email: str,
        sender_name: str,
        sandbox: bool,
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        super().__init__(
            base_url="https://api.brevo.com/v3",
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
        self.sender_email = sender_email
        self.sender_name = sender_name
        self.sandbox = sandbox

    async def send_email(self, outreach_email: OutreachEmail) -> SendResult:
        payload = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": outreach_email.to_email, "name": outreach_email.to_name}],
            "subject": outreach_email.subject,
            "textContent": outreach_email.text_body,
        }
        if outreach_email.html_body:
            payload["htmlContent"] = outreach_email.html_body

        try:
            headers = {"api-key": self.api_key, "Content-Type": "application/json"}
            if self.sandbox:
                headers["X-Sib-Sandbox"] = "drop"
            data = await self.request(
                "POST",
                "/smtp/email",
                headers=headers,
                json=payload,
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            if "sender" in detail.lower() or "verified" in detail.lower():
                raise EmailSendError("Brevo sender or domain is not verified") from exc
            raise

        return SendResult(
            email=outreach_email.to_email,
            status="sent",
            provider_message_id=data.get("messageId") or data.get("message_id"),
            error=None,
        )
