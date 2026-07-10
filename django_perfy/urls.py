from django.urls import include, path
from typing import List

urlpatterns: List[path] = [
    path("", include("django_perfy.dashboard.urls", namespace="dashboard")),
    path(
        "reports/",
        include("django_perfy.reports.urls", namespace="reports"),
    ),
]
