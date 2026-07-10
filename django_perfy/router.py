"""Database routing for the performance app.

The app registers all of its models under the ``performance`` app label. This
router keeps every read, write and migration for that label pinned to a single
alias — ``PERFORMANCE_MONITOR["DATABASE"]`` — so a project can push telemetry
into a secondary database without any per-query ``using()`` calls.

When the alias is left at the default ``"default"`` the router is a no-op: it
returns ``None`` for routing decisions and ``allow_migrate`` behaves like stock
Django, so nothing changes for single-database projects.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

from django_perfy.utils import get_database_alias

#: The app label every performance model declares in ``Meta.app_label``.
PERFORMANCE_APP_LABEL: str = "performance"

#: Dotted path used when auto-registering into ``settings.DATABASE_ROUTERS``.
ROUTER_PATH: str = "django_perfy.router.PerformanceRouter"


class PerformanceRouter:
    """Pin the ``performance`` app to its configured database alias."""

    app_label: str = PERFORMANCE_APP_LABEL

    def _target_alias(self) -> str:
        return get_database_alias()

    def db_for_read(self, model: Any, **hints: Any) -> str | None:
        if model._meta.app_label == self.app_label:
            return self._target_alias()
        return None

    def db_for_write(self, model: Any, **hints: Any) -> str | None:
        if model._meta.app_label == self.app_label:
            return self._target_alias()
        return None

    def allow_relation(self, obj1: Any, obj2: Any, **hints: Any) -> bool | None:
        # Allow relations when both objects live on the performance alias.
        labels: set[str] = {obj1._meta.app_label, obj2._meta.app_label}
        if labels == {self.app_label}:
            return True
        return None

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool | None:
        if app_label == self.app_label:
            # Performance tables belong only on the configured alias.
            return db == self._target_alias()
        return None


def register_router() -> None:
    """Append :class:`PerformanceRouter` to ``settings.DATABASE_ROUTERS`` once.

    Called from ``PerformanceConfig.ready()`` so a project gets multi-database
    routing for free. Registration is idempotent and invalidates Django's cached
    router chain so the change takes effect even if the chain was already built.
    """
    routers: list[Any] = list(getattr(settings, "DATABASE_ROUTERS", []))
    if ROUTER_PATH in routers or any(
        isinstance(entry, PerformanceRouter) for entry in routers
    ):
        return

    routers.append(ROUTER_PATH)
    settings.DATABASE_ROUTERS = routers

    # Drop Django's cached router chain so the new entry is picked up even when
    # a query has already forced the chain to build.
    from django.db import router as connection_router

    connection_router._routers = None
    connection_router.__dict__.pop("routers", None)
