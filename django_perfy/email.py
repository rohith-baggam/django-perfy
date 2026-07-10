"""SMTP delivery for performance reports.

Credentials come from the ``PERFORMANCE_MONITOR`` settings block and fall back
to the project's top-level ``EMAIL_*`` settings when a value is left blank. When
``EMAIL_ENABLED`` is off, or a host cannot be resolved, we raise
:class:`EmailNotConfigured` instead of failing silently so a misconfigured
mailer surfaces loudly in task logs.
"""

from __future__ import annotations

from typing import Any, Iterable

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from django_perfy.utils import get_settings


class EmailNotConfigured(RuntimeError):
    """Raised when report email is requested but no usable SMTP config exists."""


class Attachment(dict):
    """Typed alias for the attachment dicts accepted by :func:`send_email`.

    Keys: ``filename`` (str), ``data`` (bytes), ``content_type`` (str).
    """


def _resolve(key: str, django_key: str | None = None, default: Any = None) -> Any:
    """Return the performance block value, or the Django setting, or a default."""
    cfg: dict[str, Any] = get_settings()
    value: Any = cfg.get(key)
    if value not in (None, ""):
        return value
    if django_key is not None:
        return getattr(settings, django_key, default)
    return default


def send_email(
    receiver_email: str | Iterable[str],
    subject: str,
    body: str,
    attachments: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """Send an HTML email with optional attachments over SMTP.

    Returns ``(ok, message)`` so callers keep a simple success flag. Raises
    :class:`EmailNotConfigured` when email is disabled or no host is set.
    """
    cfg: dict[str, Any] = get_settings()
    if not cfg.get("EMAIL_ENABLED", False):
        raise EmailNotConfigured(
            "PERFORMANCE_MONITOR['EMAIL_ENABLED'] is False; refusing to send a "
            "report email. Enable it and provide SMTP credentials to opt in."
        )

    host: str = _resolve("EMAIL_HOST", "EMAIL_HOST", "")
    if not host:
        raise EmailNotConfigured(
            "No SMTP host configured. Set PERFORMANCE_MONITOR['EMAIL_HOST'] or "
            "the project's EMAIL_HOST setting."
        )

    port: int = int(_resolve("EMAIL_PORT", "EMAIL_PORT", 587))
    username: str = _resolve("EMAIL_HOST_USER", "EMAIL_HOST_USER", "")
    password: str = _resolve("EMAIL_HOST_PASSWORD", "EMAIL_HOST_PASSWORD", "")
    use_tls: bool = bool(_resolve("EMAIL_USE_TLS", "EMAIL_USE_TLS", True))
    use_ssl: bool = bool(_resolve("EMAIL_USE_SSL", "EMAIL_USE_SSL", False))
    from_email: str = (
        _resolve("DEFAULT_FROM_EMAIL", "DEFAULT_FROM_EMAIL", "") or username
    )
    if not from_email:
        raise EmailNotConfigured(
            "No sender address. Set PERFORMANCE_MONITOR['DEFAULT_FROM_EMAIL'], "
            "EMAIL_HOST_USER, or the project's DEFAULT_FROM_EMAIL setting."
        )

    recipients: list[str] = (
        [receiver_email] if isinstance(receiver_email, str) else list(receiver_email)
    )

    connection = get_connection(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
    )
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=recipients,
        connection=connection,
    )
    message.content_subtype = "html"
    for attachment in attachments or []:
        message.attach(
            attachment["filename"],
            attachment["data"],
            attachment.get("content_type", "application/octet-stream"),
        )

    delivered: int = message.send(fail_silently=False)
    if not delivered:
        return False, "SMTP server accepted no recipients"
    return True, f"delivered to {len(recipients)} recipient(s)"
