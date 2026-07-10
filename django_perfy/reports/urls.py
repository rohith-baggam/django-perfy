from django.urls import path, URLPattern

from . import views

app_name: str = "reports"

urlpatterns: list[URLPattern] = [
    path("preview/", views.ReportPreviewView.as_view(), name="preview"),
    path("download/", views.ReportDownloadView.as_view(), name="download"),
    path("email/", views.ReportEmailView.as_view(), name="email"),
]
