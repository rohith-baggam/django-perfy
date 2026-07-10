from django.urls import path
from typing import List

from . import views

app_name: str = "dashboard"

urlpatterns: List = [
    path("", views.dashboard_overview, name="overview"),
    path("api-performance/", views.dashboard_api_performance, name="api_performance"),
    path("websocket/", views.dashboard_websocket, name="websocket"),
    path(
        "system-resources/",
        views.dashboard_system_resources,
        name="system_resources",
    ),
    path(
        "database-queries/",
        views.dashboard_database_queries,
        name="database_queries",
    ),
    path("correlation/", views.dashboard_correlation, name="correlation"),
    path("raw-logs/", views.dashboard_raw_logs, name="raw_logs"),
    path("api/overview/", views.api_overview_data, name="api_overview"),
    path(
        "api/api-performance/",
        views.api_api_performance_data,
        name="api_api_performance",
    ),
    path("api/websocket/", views.api_websocket_data, name="api_websocket"),
    path("api/resources/", views.api_resources_data, name="api_resources"),
    path("api/db-queries/", views.api_db_data, name="api_db_queries"),
    path("api/correlation/", views.api_correlation_data, name="api_correlation"),
    path("api/raw-logs/", views.api_raw_logs_data, name="api_raw_logs"),
]
