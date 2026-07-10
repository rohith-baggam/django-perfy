from __future__ import annotations

import functools
import hashlib
import hmac
import random
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
}


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
