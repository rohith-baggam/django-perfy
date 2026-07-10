"""Django settings for the django-perfy test project.

Wires the package the same way a host project would: a Jinja2 backend for the
dashboard, ``STATICFILES_DIRS`` for its assets, and a secondary ``performance``
database so the router is exercised end to end.
"""

from __future__ import annotations

import django_perfy

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_perfy",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "tests.urls"

# Two databases so the PerformanceRouter has somewhere to route to. The
# performance app's tables land only on the "performance" alias.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
    "performance": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

PERFORMANCE_MONITOR = {
    "ENABLED": True,
    "SAMPLING_RATE": 1.0,
    "SLOW_REQUEST_THRESHOLD_MS": 500,
    "EXCLUDED_PATHS": ["/health/", "/metrics/", "/favicon.ico"],
    "RETENTION_DAYS_RAW": 30,
    "RETENTION_DAYS_RESOURCES": 90,
    "QUEUE_NAME": "performance_logs",
    "USER_ID_SALT": "test-salt",
    "SERVICES": [],
    # Route all telemetry to the secondary database.
    "DATABASE": "performance",
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [django_perfy.DASHBOARD_TEMPLATES_DIR],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "django_perfy.dashboard.jinja2_env.make_environment",
            "autoescape": True,
        },
    },
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "/static/"
STATICFILES_DIRS = [django_perfy.DASHBOARD_STATIC_DIR]

# Run Celery tasks inline so tests don't need a broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
