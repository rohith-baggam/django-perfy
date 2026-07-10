from __future__ import annotations

from django.db import models


class APIRequestLog(models.Model):
    endpoint = models.CharField(max_length=255, db_index=True)
    method = models.CharField(max_length=10)
    status_code = models.PositiveSmallIntegerField()
    response_time_ms = models.PositiveIntegerField()
    request_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    response_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    db_query_count = models.PositiveIntegerField(default=0)
    db_time_ms = models.PositiveIntegerField(default=0)
    concurrent_requests = models.PositiveIntegerField(default=0)
    user_hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "performance"
        indexes = [
            models.Index(fields=["endpoint", "created_at"]),
            models.Index(fields=["created_at", "response_time_ms"]),
            models.Index(fields=["status_code", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.endpoint} {self.status_code} {self.response_time_ms}ms"


class WebSocketEventLog(models.Model):
    EVENT_CONNECT = "connect"
    EVENT_DISCONNECT = "disconnect"
    EVENT_RECEIVE = "receive"
    EVENT_SEND = "send"
    EVENT_CHOICES = [
        (EVENT_CONNECT, "Connect"),
        (EVENT_DISCONNECT, "Disconnect"),
        (EVENT_RECEIVE, "Receive"),
        (EVENT_SEND, "Send"),
    ]

    DIRECTION_INBOUND = "inbound"
    DIRECTION_OUTBOUND = "outbound"
    DIRECTION_CHOICES = [
        (DIRECTION_INBOUND, "Inbound"),
        (DIRECTION_OUTBOUND, "Outbound"),
    ]

    consumer_name = models.CharField(max_length=100, db_index=True)
    connection_id = models.UUIDField(db_index=True)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    message_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    processing_time_ms = models.PositiveIntegerField(null=True, blank=True)
    connection_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    user_hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "performance"
        indexes = [
            models.Index(fields=["consumer_name", "created_at"]),
            models.Index(fields=["connection_id", "created_at"]),
            models.Index(fields=["created_at", "processing_time_ms"]),
        ]

    def __str__(self) -> str:
        return f"{self.consumer_name} {self.event_type} {self.direction}"


class SystemResourceSnapshot(models.Model):
    TYPE_WEB = "web"
    TYPE_CELERY_WORKER = "celery_worker"
    TYPE_CELERY_BEAT = "celery_beat"
    TYPE_REDIS = "redis"
    TYPE_POSTGRES = "postgres"
    TYPE_SYSTEM = "system"
    TYPE_CHOICES = [
        (TYPE_WEB, "Web"),
        (TYPE_CELERY_WORKER, "Celery Worker"),
        (TYPE_CELERY_BEAT, "Celery Beat"),
        (TYPE_REDIS, "Redis"),
        (TYPE_POSTGRES, "Postgres"),
        (TYPE_SYSTEM, "System"),
    ]

    service_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    service_name = models.CharField(max_length=100)
    instance_id = models.CharField(max_length=200, null=True, blank=True)

    cpu_percent = models.DecimalField(max_digits=5, decimal_places=2)
    ram_used_mb = models.PositiveIntegerField()
    ram_total_mb = models.PositiveIntegerField()
    ram_percent = models.DecimalField(max_digits=5, decimal_places=2)

    disk_used_gb = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    disk_total_gb = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True
    )
    disk_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    open_file_descriptors = models.PositiveIntegerField(null=True, blank=True)
    active_threads = models.PositiveIntegerField(null=True, blank=True)

    celery_active_tasks = models.PositiveIntegerField(null=True, blank=True)
    celery_queued_tasks = models.PositiveIntegerField(null=True, blank=True)
    celery_reserved_tasks = models.PositiveIntegerField(null=True, blank=True)

    redis_used_memory_mb = models.PositiveIntegerField(null=True, blank=True)
    redis_connected_clients = models.PositiveIntegerField(null=True, blank=True)
    redis_blocked_clients = models.PositiveIntegerField(null=True, blank=True)

    postgres_active_connections = models.PositiveIntegerField(null=True, blank=True)
    postgres_idle_connections = models.PositiveIntegerField(null=True, blank=True)
    postgres_db_size_mb = models.PositiveIntegerField(null=True, blank=True)

    captured_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "performance"
        indexes = [
            models.Index(fields=["service_type", "service_name", "captured_at"]),
            models.Index(fields=["captured_at", "cpu_percent"]),
            models.Index(fields=["captured_at", "ram_percent"]),
        ]

    def __str__(self) -> str:
        return f"{self.service_type}/{self.service_name} @ {self.captured_at}"


class PerformanceSummary(models.Model):
    LOG_TYPE_API = "api"
    LOG_TYPE_WEBSOCKET = "websocket"
    LOG_TYPE_CHOICES = [
        (LOG_TYPE_API, "API"),
        (LOG_TYPE_WEBSOCKET, "WebSocket"),
    ]

    GRANULARITY_MINUTE = "minute"
    GRANULARITY_HOUR = "hour"
    GRANULARITY_CHOICES = [
        (GRANULARITY_MINUTE, "Minute"),
        (GRANULARITY_HOUR, "Hour"),
    ]

    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES)
    endpoint_or_consumer = models.CharField(max_length=255)
    granularity = models.CharField(max_length=10, choices=GRANULARITY_CHOICES)
    window_start = models.DateTimeField()

    total_requests = models.PositiveIntegerField(default=0)
    avg_response_time_ms = models.PositiveIntegerField(default=0)
    p50_ms = models.PositiveIntegerField(default=0)
    p95_ms = models.PositiveIntegerField(default=0)
    p99_ms = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    avg_request_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    avg_response_size_bytes = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "performance"
        unique_together = [
            ("log_type", "endpoint_or_consumer", "granularity", "window_start")
        ]
        indexes = [
            models.Index(fields=["log_type", "endpoint_or_consumer", "window_start"]),
            models.Index(fields=["window_start", "p99_ms"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.log_type} {self.endpoint_or_consumer} "
            f"{self.granularity} @ {self.window_start}"
        )
