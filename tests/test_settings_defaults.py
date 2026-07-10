"""Settings merging and the DATABASE alias helper."""

from __future__ import annotations

from django.test import override_settings

from django_perfy.utils import get_database_alias, get_settings


def test_defaults_are_filled_in() -> None:
    cfg = get_settings()
    assert cfg["SAMPLING_RATE"] == 1.0  # from tests.settings
    assert cfg["RETENTION_DAYS_RAW"] == 30  # from _DEFAULTS
    assert cfg["MONITOR_POSTGRES"] is True  # from _DEFAULTS


def test_database_alias_from_settings() -> None:
    assert get_database_alias() == "performance"


@override_settings(PERFORMANCE_MONITOR={})
def test_database_alias_defaults_to_default() -> None:
    assert get_database_alias() == "default"
