from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def collect_process_metrics(service_name: str, service_type: str) -> dict[str, Any]:
    import psutil

    proc = psutil.Process(os.getpid())

    # psutil.Process.cpu_percent() is relative to a single core, so a process
    # using several cores can read well past 100% (e.g. 201.6% on 2 cores
    # saturated). Normalize by logical core count so this reads the same way
    # Zabbix/Prometheus/node_exporter report process CPU: 0-100% of total
    # host capacity.
    cpu_cores = psutil.cpu_count() or 1
    cpu = proc.cpu_percent(interval=0.1) / cpu_cores
    mem = proc.memory_info()
    ram_used_mb = mem.rss // (1024 * 1024)

    virtual_mem = psutil.virtual_memory()
    ram_total_mb = virtual_mem.total // (1024 * 1024)
    ram_percent = float(virtual_mem.percent)

    try:
        disk = psutil.disk_usage("/")
        disk_used_gb: float | None = round(disk.used / (1024**3), 3)
        disk_total_gb: float | None = round(disk.total / (1024**3), 3)
        disk_percent: float | None = float(disk.percent)
    except Exception:
        disk_used_gb: float | None = None
        disk_total_gb: float | None = None
        disk_percent: float | None = None

    try:
        open_fds: int | None = proc.num_fds()
    except Exception:
        open_fds: None = None

    active_threads = proc.num_threads()

    celery_active: int | None = None
    celery_queued: int | None = None
    celery_reserved: int | None = None
    if service_type in ("celery_worker", "celery_beat"):
        try:
            from celery import current_app

            inspect = current_app.control.inspect(timeout=1.0)
            active_map = inspect.active() or {}
            reserved_map = inspect.reserved() or {}
            active_tasks = sum(len(v) for v in active_map.values())
            reserved_tasks = sum(len(v) for v in reserved_map.values())

            queued_tasks: int = 0
            try:
                with current_app.connection_or_connect() as conn:
                    for queue in current_app.conf.task_queues or []:
                        q = conn.SimpleQueue(queue.name)
                        queued_tasks += q.qsize()
            except Exception:
                pass

            celery_active = active_tasks
            celery_reserved: int = reserved_tasks
            celery_queued: int = queued_tasks
        except Exception as exc:
            logger.debug("collect_process_metrics: celery inspect failed: %s", exc)

    return {
        "service_type": service_type,
        "service_name": service_name,
        "instance_id": os.environ.get("INSTANCE_ID") or os.environ.get("HOSTNAME"),
        "cpu_percent": round(cpu, 2),
        "ram_used_mb": ram_used_mb,
        "ram_total_mb": ram_total_mb,
        "ram_percent": round(ram_percent, 2),
        "disk_used_gb": disk_used_gb,
        "disk_total_gb": disk_total_gb,
        "disk_percent": disk_percent,
        "open_file_descriptors": open_fds,
        "active_threads": active_threads,
        "celery_active_tasks": celery_active,
        "celery_queued_tasks": celery_queued,
        "celery_reserved_tasks": celery_reserved,
        "captured_at": datetime.now(tz=timezone.utc),
    }


def collect_redis_metrics() -> dict[str, Any]:
    import redis as redis_lib
    from django.conf import settings

    broker_url: str = getattr(settings, "CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    try:
        client = redis_lib.Redis.from_url(broker_url, socket_connect_timeout=2)
        info = client.info()
        used_memory_mb: int | None = info.get("used_memory", 0) // (1024 * 1024)
        connected_clients: int = info.get("connected_clients", 0)
        blocked_clients: int = info.get("blocked_clients", 0)
    except Exception as exc:
        logger.warning("collect_redis_metrics failed: %s", exc)
        used_memory_mb: int | None = None
        connected_clients: int = None
        blocked_clients: int = None

    return {
        "service_type": "redis",
        "service_name": "redis",
        "instance_id": None,
        "cpu_percent": 0,
        "ram_used_mb": used_memory_mb or 0,
        "ram_total_mb": 0,
        "ram_percent": 0,
        "redis_used_memory_mb": used_memory_mb,
        "redis_connected_clients": connected_clients,
        "redis_blocked_clients": blocked_clients,
        "captured_at": datetime.now(tz=timezone.utc),
    }


def collect_postgres_metrics() -> dict[str, Any]:
    from django.db import connection

    active_connections: int | None = None
    idle_connections: int | None = None
    db_size_mb: int | None = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
            )
            active_connections = cursor.fetchone()[0]

            cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE state = 'idle'")
            idle_connections = cursor.fetchone()[0]

            cursor.execute(
                "SELECT pg_database_size(current_database()) / (1024 * 1024)"
            )
            db_size_mb = cursor.fetchone()[0]
    except Exception as exc:
        logger.warning("collect_postgres_metrics failed: %s", exc)

    return {
        "service_type": "postgres",
        "service_name": "postgres",
        "instance_id": None,
        "cpu_percent": 0,
        "ram_used_mb": 0,
        "ram_total_mb": 0,
        "ram_percent": 0,
        "postgres_active_connections": active_connections,
        "postgres_idle_connections": idle_connections,
        "postgres_db_size_mb": db_size_mb,
        "captured_at": datetime.now(tz=timezone.utc),
    }
