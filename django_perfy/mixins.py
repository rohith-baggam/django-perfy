from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _performance_enabled() -> bool:
    try:
        from django_perfy.utils import get_settings

        return bool(get_settings().get("ENABLED", True))
    except Exception:
        return False


async def _write_ws_log(payload: dict) -> None:
    """Background coroutine: direct DB write, no Celery dependency."""
    if not _performance_enabled():
        return
    try:
        from asgiref.sync import sync_to_async
        from django_perfy.models import WebSocketEventLog

        await sync_to_async(WebSocketEventLog.objects.create)(**payload)
    except Exception as exc:
        logger.warning("WebSocketLoggingMixin: DB write failed: %s", exc)


class WebSocketLoggingMixin:
    """
    Mixin for Django Channels AsyncWebsocketConsumer subclasses.

    Usage:
        class MyConsumer(WebSocketLoggingMixin, BaseAsyncWebsocketConsumer): ...

    Wraps the low-level Channels dispatch handlers (websocket_connect,
    websocket_disconnect, websocket_receive) rather than the application-level
    connect/disconnect/receive methods — this ensures instrumentation fires even
    when consumers override those application-level methods without calling super().
    """

    def _perf_consumer_name(self) -> str:
        return type(self).__name__

    def _perf_user_hash(self) -> str | None:
        try:
            from django_perfy.utils import hash_user_id

            user = getattr(self, "user", None)
            if user is None:
                return None
            uid = getattr(user, "user_id", None) or getattr(user, "pk", None)
            if uid is None:
                return None
            return hash_user_id(uid)
        except Exception:
            return None

    def _perf_schedule(self, payload: dict) -> None:
        """Schedule a background DB write without blocking the async event loop."""
        if not _performance_enabled():
            return
        try:
            conn_id = getattr(self, "_perf_connection_id", None)
            payload["connection_id"] = str(conn_id) if conn_id else str(uuid.uuid4())
            payload["consumer_name"] = self._perf_consumer_name()
            payload["user_hash"] = self._perf_user_hash()
            asyncio.ensure_future(_write_ws_log(payload))
        except Exception as exc:
            logger.debug("WebSocketLoggingMixin: schedule failed: %s", exc)

    # ------------------------------------------------------------------
    # Low-level Channels dispatch handlers — consumers do NOT override
    # these, so the mixin's instrumentation is always reached.
    # ------------------------------------------------------------------

    async def websocket_connect(self, message: dict[str, Any]) -> None:
        self._perf_connection_id = uuid.uuid4()
        self._perf_connect_time = time.perf_counter()
        start = time.perf_counter()
        try:
            await super().websocket_connect(message)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._perf_schedule(
                {
                    "event_type": "connect",
                    "direction": "inbound",
                    "processing_time_ms": elapsed_ms,
                }
            )

    async def websocket_disconnect(self, message: dict[str, Any]) -> None:
        start = time.perf_counter()
        connect_time = getattr(self, "_perf_connect_time", None)
        try:
            await super().websocket_disconnect(message)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            connection_duration_ms = (
                int((time.perf_counter() - connect_time) * 1000)
                if connect_time is not None
                else None
            )
            self._perf_schedule(
                {
                    "event_type": "disconnect",
                    "direction": "inbound",
                    "processing_time_ms": elapsed_ms,
                    "connection_duration_ms": connection_duration_ms,
                }
            )

    async def websocket_receive(self, message: dict[str, Any]) -> None:
        """
        Low-level handler called by Channels for every inbound frame.
        Channels dispatches here before calling self.receive(), so this
        fires regardless of whether the consumer overrides receive().
        """
        start = time.perf_counter()
        raw = message.get("text") or message.get("bytes") or b""
        size = len(raw.encode("utf-8") if isinstance(raw, str) else raw)
        try:
            await super().websocket_receive(message)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._perf_schedule(
                {
                    "event_type": "receive",
                    "direction": "inbound",
                    "message_size_bytes": size,
                    "processing_time_ms": elapsed_ms,
                }
            )

    async def send(
        self,
        text_data: str | None = None,
        bytes_data: bytes | None = None,
        close: bool = False,
    ) -> None:
        """
        Application-level send — consumers call self.send() to push data to
        the client. Consumers do not override this method, so wrapping it here
        always fires.
        """
        start = time.perf_counter()
        size = (
            len(text_data.encode("utf-8"))
            if text_data
            else (len(bytes_data) if bytes_data else 0)
        )
        try:
            await super().send(text_data=text_data, bytes_data=bytes_data, close=close)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            self._perf_schedule(
                {
                    "event_type": "send",
                    "direction": "outbound",
                    "message_size_bytes": size,
                    "processing_time_ms": elapsed_ms,
                }
            )
