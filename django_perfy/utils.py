from __future__ import annotations

import functools
import hashlib
import hmac
import json
import random
import socket
from typing import Any

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver

_DEFAULTS: dict[str, Any] = {
    "ENABLED": True,
    "SAMPLING_RATE": 0.1,
    "SLOW_REQUEST_THRESHOLD_MS": 500,
    "EXCLUDED_PATHS": ["/health/", "/metrics/", "/favicon.ico"],
    "RETENTION_DAYS_RAW": 30,
    "RETENTION_DAYS_RESOURCES": 90,
    "QUEUE_NAME": "performance_logs",
    "USER_ID_SALT": "changeme-in-prod",
    "ENABLE_PARTITIONING": False,
    "RESOURCE_SNAPSHOT_INTERVAL_MINUTES": 15,
    "SERVICES": [],
    "MONITOR_POSTGRES": True,
    "MONITOR_REDIS": True,
    # Database alias every performance model reads from and writes to. Keep it
    # on "default" to co-locate telemetry with the app, or point it at a
    # secondary alias declared in settings.DATABASES to isolate the write load.
    "DATABASE": "default",
    # Report emailing. Credentials are read from this block first and fall back
    # to the project's top-level EMAIL_* settings when a value is left blank.
    "EMAIL_ENABLED": False,
    "EMAIL_HOST": "",
    "EMAIL_PORT": 587,
    "EMAIL_HOST_USER": "",
    "EMAIL_HOST_PASSWORD": "",
    "EMAIL_USE_TLS": True,
    "EMAIL_USE_SSL": False,
    "DEFAULT_FROM_EMAIL": "",
    # Request/response header capture. Off by default — headers routinely carry
    # session cookies, auth tokens and API keys, so this is opt-in.
    "CAPTURE_HEADERS": False,
    # Header names (case-insensitive) stored as "[REDACTED]" instead of their
    # real value when CAPTURE_HEADERS is on. Extend, don't replace, via
    # settings.PERFORMANCE_MONITOR["REDACTED_HEADERS"].
    "REDACTED_HEADERS": [
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "proxy-authorization",
        "x-csrftoken",
    ],
    # Request/response body capture. Off by default and independent of
    # CAPTURE_HEADERS — bodies are higher-sensitivity (full payloads, not just
    # metadata) and higher-volume to store.
    "CAPTURE_BODY": False,
    # Bodies are truncated to this many bytes before storage.
    "MAX_BODY_BYTES": 8192,
    # JSON field names (case-insensitive) whose values are replaced with
    # "[REDACTED]" when a captured body parses as JSON.
    "REDACTED_BODY_FIELDS": [
        "password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "card_number",
        "cvv",
        "cvv2",
        "ssn",
        "pin",
    ],
    # Backend IP recorded on every captured row. Auto-detected from the host
    # when left blank — set explicitly if auto-detection picks the wrong
    # interface (e.g. behind Docker/NAT).
    "SERVER_IP": None,
}

_BINARY_CONTENT_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "font/",
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "multipart/form-data",
)


@functools.lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    user_cfg: dict[str, Any] = getattr(settings, "PERFORMANCE_MONITOR", {})
    merged: dict[str, Any] = {**_DEFAULTS, **user_cfg}
    return merged


@receiver(setting_changed)
def _reset_settings_cache(*, setting: str, **kwargs: Any) -> None:
    """Drop the cached config when PERFORMANCE_MONITOR changes at runtime.

    Keeps ``override_settings`` honest in tests and lets deployments that reload
    settings pick up new values without a process restart.
    """
    if setting == "PERFORMANCE_MONITOR":
        get_settings.cache_clear()
        get_server_ip.cache_clear()


def get_database_alias() -> str:
    """Return the DATABASES alias every performance model should bind to.

    Defaults to ``"default"``. When a project points this at a secondary alias
    the bundled router (:class:`django_perfy.router.PerformanceRouter`) keeps
    reads, writes and migrations for the ``performance`` app on that database.
    """
    alias: str = get_settings().get("DATABASE") or "default"
    return alias


def normalize_url(request) -> str:
    try:
        if request.resolver_match and request.resolver_match.route:
            return request.resolver_match.route[:255]
    except Exception:
        pass
    return request.path[:255]


def hash_user_id(user_id) -> str:
    salt = get_settings()["USER_ID_SALT"]
    return hmac.new(
        salt.encode("utf-8"),
        str(user_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def should_sample(response_time_ms: int, status_code: int) -> bool:
    cfg = get_settings()
    if response_time_ms >= cfg["SLOW_REQUEST_THRESHOLD_MS"]:
        return True
    if status_code >= 400:
        return True
    return random.random() < cfg["SAMPLING_RATE"]


def redact_headers(headers: dict[str, Any]) -> dict[str, str]:
    """Copy ``headers`` with sensitive values replaced by ``[REDACTED]``.

    Header names in ``REDACTED_HEADERS`` are matched case-insensitively so a
    project can list them in either case in settings.
    """
    redact_names = {name.lower() for name in get_settings()["REDACTED_HEADERS"]}
    return {
        key: ("[REDACTED]" if key.lower() in redact_names else str(value))
        for key, value in headers.items()
    }


def _redact_json_value(value: Any, redact_names: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k.lower() in redact_names else _redact_json_value(v, redact_names))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_json_value(v, redact_names) for v in value]
    return value


def redact_body(raw: bytes | None, content_type: str) -> str | None:
    """Best-effort text form of a request/response body, redacted and capped.

    Returns ``None`` for empty/binary bodies. JSON bodies have sensitive keys
    (``REDACTED_BODY_FIELDS``) replaced; anything else is captured as truncated
    raw text, since a body isn't always JSON (form-encoded, HTML error pages).
    """
    if not raw:
        return None
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type.startswith(_BINARY_CONTENT_PREFIXES):
        return "[binary omitted]"

    cfg = get_settings()
    max_bytes: int = cfg["MAX_BODY_BYTES"]
    redact_names = {name.lower() for name in cfg["REDACTED_BODY_FIELDS"]}

    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            pass
        else:
            text = json.dumps(_redact_json_value(parsed, redact_names), ensure_ascii=False)
            return text if len(text) <= max_bytes else text[:max_bytes] + "…[truncated]"

    try:
        text = raw[:max_bytes].decode("utf-8", errors="replace")
    except Exception:
        return "[unreadable body]"
    return text + "…[truncated]" if len(raw) > max_bytes else text


@functools.lru_cache(maxsize=1)
def get_server_ip() -> str | None:
    """Best-effort backend IP: explicit setting, else the host's own address."""
    configured = get_settings().get("SERVER_IP")
    if configured:
        return configured
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception:
        return None
