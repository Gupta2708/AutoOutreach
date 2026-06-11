from __future__ import annotations

from rich.console import Console

from app.services.safety import confirm_send


def test_safety_confirmation_requires_exact_send() -> None:
    console = Console(record=True)
    assert confirm_send(console=console, ask=lambda: "send") is False
    assert confirm_send(console=console, ask=lambda: "SEND") is True
