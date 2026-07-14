# Installation

This page covers installing django-perfy, its optional extras, the system
libraries the PDF reports need, and the migration steps — including the one
that is easy to miss when telemetry lives in a secondary database. For a
condensed path from install to first request, see
[Getting started](getting-started.md); for the full dependency list, see
[Dependencies](dependencies.md).

<video controls preload="metadata" playsinline style="width:100%;border-radius:8px;margin:1rem 0">
  <source src="../assets/videos/installation.mp4" type="video/mp4">
  Your browser does not support the video tag.
  <a href="../assets/videos/installation.mp4">Download the installation video</a>.
</video>

## Install with pip

django-perfy is published on PyPI at
<https://pypi.org/project/django-perfy/>.

```bash
pip install django-perfy            # core: middleware, mixin, models, tasks
pip install "django-perfy[reports]" # + dashboard and PDF reports
```

The core install gives you the middleware, the WebSocket mixin, the models and
the Celery tasks. The dashboard and PDF reports live behind the `reports`
extra.

### Available extras

| Extra | Pulls in | Use it for |
| --- | --- | --- |
| `reports` | `jinja2`, `weasyprint` | The staff dashboard and PDF report engine |
| `dashboard` | `jinja2` | The dashboard only (HTML, no PDF) |
| `all` | `jinja2`, `weasyprint` | A full deployment |
| `dev` | test and lint tooling | Local development on the package |
| `docs` | `mkdocs-material` | Building this documentation site |

!!! warning "WeasyPrint needs system libraries"
    PDF rendering goes through
    [WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/), which
    depends on Pango and Cairo at the operating-system level — `pip install`
    alone does not satisfy that on most systems. Follow WeasyPrint's own
    [installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation)
    for your platform before relying on PDF downloads. The dashboard's HTML
    *preview* works without these libraries, since the renderer imports
    WeasyPrint lazily — only the download and email paths need it.

## Add the app

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "django_perfy",
]
```

## Add the middleware

```python
MIDDLEWARE = [
    # ... after AuthenticationMiddleware so request.user is available ...
    "django_perfy.middleware.PerformanceMiddleware",
]
```

Place it after `AuthenticationMiddleware`; the middleware reads
`request.user` to record an anonymized user hash on authenticated requests.

## Run migrations

```bash
python manage.py migrate
```

!!! tip "Using a secondary database? Migrate the alias too"
    If `PERFORMANCE_MONITOR["DATABASE"]` points at a secondary alias, the
    package's tables are pinned there by the bundled router and **will not** be
    created by a plain `migrate`. Run the alias explicitly as well — this is
    the single easiest step to forget:

    ```bash
    python manage.py migrate --database=performance
    ```

    See [Secondary database](guides/secondary-database.md) for the full setup.

## Mount the dashboard (optional)

The dashboard needs the `reports` (or `dashboard`) extra and a Jinja2 template
backend. Full wiring — the `TEMPLATES` block, static assets and URLs — is in
[Dashboard & reports](features/dashboard-and-reports.md). In short:

```python
# urls.py
urlpatterns += [path("performance/", include("django_perfy.urls"))]
```

!!! warning "Static files under gunicorn/uWSGI/daphne"
    `runserver` serves the dashboard's CSS and JS automatically, but a
    production WSGI/ASGI app server (gunicorn, uWSGI, daphne) does not serve
    static files at all — under those the dashboard loads unstyled until you
    run `collectstatic` and serve `STATIC_ROOT` (for example with WhiteNoise or
    nginx). This is standard Django behaviour. See
    [Dashboard & reports](features/dashboard-and-reports.md#serving-those-static-files-important-under-gunicornuwsgi).

    ```bash
    python manage.py collectstatic --noinput
    ```

## Verify the configuration

`PERFORMANCE_MONITOR` is validated by Django's system-check framework, so a
typo or wrong type surfaces before runtime:

```bash
python manage.py check
```

See the [settings reference](reference/settings.md) for the checks
(`performance.E001`–`E006`) and every configurable key.

## Next steps

- [Configuration](configuration.md) — the full option set, explained.
- [Getting started](getting-started.md) — the quickstart path.
- [Background](background.md) — watch the installation walkthrough end to end.
