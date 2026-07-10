from __future__ import annotations

from django.core.checks import Error, register

VALID_SERVICE_TYPES = {
    "web",
    "celery_worker",
    "celery_beat",
    "redis",
    "postgres",
    "system",
}
REQUIRED_KEYS = {
    "ENABLED": bool,
    "SAMPLING_RATE": (int, float),
    "SLOW_REQUEST_THRESHOLD_MS": int,
    "EXCLUDED_PATHS": list,
    "RETENTION_DAYS_RAW": int,
    "RETENTION_DAYS_RESOURCES": int,
    "QUEUE_NAME": str,
    "USER_ID_SALT": str,
    "SERVICES": list,
}


@register()
def check_performance_monitor_settings(app_configs, **kwargs):
    from django.conf import settings

    errors: list[Error] = []
    cfg = getattr(settings, "PERFORMANCE_MONITOR", None)
    if cfg is None:
        return errors

    for key, expected_type in REQUIRED_KEYS.items():
        if key not in cfg:
            errors.append(
                Error(
                    f"PERFORMANCE_MONITOR is missing required key '{key}'.",
                    id="performance.E001",
                )
            )
            continue
        if not isinstance(cfg[key], expected_type):
            errors.append(
                Error(
                    f"PERFORMANCE_MONITOR['{key}'] must be {expected_type}, "
                    f"got {type(cfg[key]).__name__}.",
                    id="performance.E002",
                )
            )

    sampling_rate = cfg.get("SAMPLING_RATE")
    if isinstance(sampling_rate, (int, float)) and not (0.0 <= sampling_rate <= 1.0):
        errors.append(
            Error(
                "PERFORMANCE_MONITOR['SAMPLING_RATE'] must be between 0.0 and 1.0.",
                id="performance.E003",
            )
        )

    services = cfg.get("SERVICES", [])
    if isinstance(services, list):
        for i, svc in enumerate(services):
            if not isinstance(svc, dict):
                errors.append(
                    Error(
                        f"PERFORMANCE_MONITOR['SERVICES'][{i}] must be a dict.",
                        id="performance.E004",
                    )
                )
                continue
            svc_type = svc.get("type")
            if svc_type not in VALID_SERVICE_TYPES:
                errors.append(
                    Error(
                        f"PERFORMANCE_MONITOR['SERVICES'][{i}]['type'] = '{svc_type}' "
                        f"is not valid. Choose from: {sorted(VALID_SERVICE_TYPES)}.",
                        id="performance.E005",
                    )
                )
            if not svc.get("name"):
                errors.append(
                    Error(
                        f"PERFORMANCE_MONITOR['SERVICES'][{i}] is missing 'name'.",
                        id="performance.E006",
                    )
                )

    return errors
