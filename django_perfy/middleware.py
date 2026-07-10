from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_concurrent = threading.local()

# Bounded thread pool for non-blocking DB writes — isolated from the request thread.
# max_workers=4 is sufficient: each write is a single INSERT, typically <5ms.
_log_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="perf-log",
)


def _write_api_log(payload: dict) -> None:
    try:
        from django.db import close_old_connections

        from django_perfy.models import APIRequestLog

        close_old_connections()
        APIRequestLog.objects.create(**payload)
    except Exception as exc:
        logger.warning("PerformanceMiddleware: DB write failed: %s", exc)


class _DBQueryWrapper:
    """Callable that plugs into Django's connection.execute_wrapper protocol."""

    def __init__(self) -> None:
        self.count = 0
        self.total_ms = 0

    def __call__(self, execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.count += 1
            self.total_ms += int((time.perf_counter() - start) * 1000)


class PerformanceMiddleware:
    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response
        self._disabled = False
        self._excluded_paths: list[str] = []

        try:
            from django_perfy.utils import get_settings

            cfg = get_settings()
            if not cfg.get("ENABLED", True):
                self._disabled = True
                return

            self._excluded_paths = cfg.get("EXCLUDED_PATHS", [])
        except Exception as exc:
            logger.warning("PerformanceMiddleware: init failed, disabling: %s", exc)
            self._disabled = True

    def _is_excluded(self, path: str) -> bool:
        for prefix in self._excluded_paths:
            if path.startswith(prefix):
                return True
        return False

    def __call__(self, request):
        if self._disabled:
            return self.get_response(request)

        try:
            path: str = request.path
        except Exception:
            return self.get_response(request)

        if self._is_excluded(path):
            return self.get_response(request)

        _concurrent.count = getattr(_concurrent, "count", 0) + 1
        start = time.perf_counter()
        db_wrapper = _DBQueryWrapper()

        from django.db import connection

        try:
            with connection.execute_wrapper(db_wrapper):
                response = self.get_response(request)
        except Exception:
            _concurrent.count = max(0, getattr(_concurrent, "count", 1) - 1)
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        concurrent = getattr(_concurrent, "count", 1)
        _concurrent.count = max(0, concurrent - 1)

        try:
            from django_perfy.utils import (
                hash_user_id,
                normalize_url,
                should_sample,
            )

            status_code = getattr(response, "status_code", 200)
            if should_sample(elapsed_ms, status_code):
                user_hash: str | None = None
                try:
                    if request.user and request.user.is_authenticated:
                        user_hash = hash_user_id(
                            getattr(request.user, "user_id", request.user.pk)
                        )
                except Exception:
                    pass

                content_length = request.headers.get("Content-Length")
                request_size = (
                    int(content_length)
                    if content_length and content_length.isdigit()
                    else None
                )

                payload: dict[str, Any] = {
                    "endpoint": normalize_url(request),
                    "method": request.method,
                    "status_code": status_code,
                    "response_time_ms": elapsed_ms,
                    "request_size_bytes": request_size,
                    "db_query_count": db_wrapper.count,
                    "db_time_ms": db_wrapper.total_ms,
                    "concurrent_requests": concurrent,
                    "user_hash": user_hash,
                }
                # Non-blocking: submit to thread pool, never waits for result.
                _log_executor.submit(_write_api_log, payload)
        except Exception as exc:
            logger.warning("PerformanceMiddleware: dispatch failed: %s", exc)

        return response
