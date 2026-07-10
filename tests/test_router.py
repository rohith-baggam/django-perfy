"""The bundled router pins the performance app to its configured alias."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.db import router

from django_perfy.models import APIRequestLog
from django_perfy.router import PerformanceRouter


def test_router_is_registered() -> None:
    assert "django_perfy.router.PerformanceRouter" in settings.DATABASE_ROUTERS


def test_router_routes_reads_and_writes_to_alias() -> None:
    instance = PerformanceRouter()
    assert instance.db_for_read(APIRequestLog) == "performance"
    assert instance.db_for_write(APIRequestLog) == "performance"


def test_router_ignores_other_apps() -> None:
    from django.contrib.auth.models import User

    instance = PerformanceRouter()
    assert instance.db_for_read(User) is None
    assert instance.db_for_write(User) is None


def test_allow_migrate_confines_tables_to_alias() -> None:
    instance = PerformanceRouter()
    assert instance.allow_migrate("performance", "performance") is True
    assert instance.allow_migrate("default", "performance") is False
    # Other apps: no opinion.
    assert instance.allow_migrate("default", "auth") is None


@pytest.mark.django_db(databases=["default", "performance"])
def test_writes_land_on_secondary_database() -> None:
    log = APIRequestLog.objects.create(
        endpoint="/api/v1/ping/",
        method="GET",
        status_code=200,
        response_time_ms=42,
    )
    # The connection-level router agrees, and the row is readable back.
    assert router.db_for_write(APIRequestLog) == "performance"
    assert APIRequestLog.objects.using("performance").filter(pk=log.pk).exists()
