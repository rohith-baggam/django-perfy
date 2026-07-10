"""Report email is settings-driven and fails loudly when misconfigured."""

from __future__ import annotations

import pytest
from django.core import mail
from django.test import override_settings

from django_perfy.email import EmailNotConfigured, send_email


@override_settings(PERFORMANCE_MONITOR={"EMAIL_ENABLED": False})
def test_disabled_email_raises() -> None:
    with pytest.raises(EmailNotConfigured):
        send_email("to@example.com", "subject", "<p>body</p>")


@override_settings(
    EMAIL_HOST="",  # Django defaults this to "localhost"; blank it to test the guard.
    PERFORMANCE_MONITOR={"EMAIL_ENABLED": True, "EMAIL_HOST": ""},
)
def test_missing_host_raises() -> None:
    with pytest.raises(EmailNotConfigured):
        send_email("to@example.com", "subject", "<p>body</p>")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PERFORMANCE_MONITOR={
        "EMAIL_ENABLED": True,
        "EMAIL_HOST": "smtp.example.com",
        "EMAIL_HOST_USER": "reports@example.com",
        "DEFAULT_FROM_EMAIL": "reports@example.com",
    },
)
def test_configured_email_is_sent_with_attachment() -> None:
    ok, message = send_email(
        "to@example.com",
        "Latency report",
        "<p>see attached</p>",
        attachments=[
            {
                "filename": "report.pdf",
                "data": b"%PDF-1.4 fake",
                "content_type": "application/pdf",
            }
        ],
    )

    assert ok is True
    assert "delivered" in message
    assert len(mail.outbox) == 1
    sent: mail.EmailMessage = mail.outbox[0]
    assert sent.to == ["to@example.com"]
    assert sent.content_subtype == "html"
    assert sent.attachments[0][0] == "report.pdf"
