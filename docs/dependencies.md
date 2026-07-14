# Dependencies

What django-perfy requires, what installs automatically, and what is opt-in
behind an extra. Source of truth: `pyproject.toml`.

## Runtime requirements

| Requirement | Version |
| --- | --- |
| Python | 3.10+ |
| Django | 4.2+ (tested against 4.2, 5.0, 5.1, 5.2, 6.0) |

## Core dependencies

Installed automatically with `pip install django-perfy`:

| Package | Version | Why it is needed |
| --- | --- | --- |
| `Django` | `>=4.2` | The framework being monitored |
| `celery` | `>=5.2` | Persistence, aggregation, snapshot and retention tasks |
| `psutil` | `>=5.9` | CPU, memory, disk and process metrics for resource snapshots |
| `redis` | `>=4.5` | Redis metrics collection and the default Celery broker client |

!!! note "Celery and Redis are dependencies, not a requirement to run them"
    These packages install so the tasks and collectors can import, but a
    running Celery worker or Beat scheduler is optional — a built-in background
    timer keeps the dashboard populated without them. See
    [Celery setup](guides/celery-setup.md) for exactly what needs Beat and what
    does not.

## Optional extras

Install with `pip install "django-perfy[<extra>]"`:

| Extra | Adds | For |
| --- | --- | --- |
| `reports` | `jinja2>=3.1`, `weasyprint>=60` | The staff dashboard and PDF report engine |
| `dashboard` | `jinja2>=3.1` | The dashboard HTML pages only (no PDF) |
| `all` | `jinja2>=3.1`, `weasyprint>=60` | A full deployment |
| `dev` | `pytest`, `pytest-django`, `black`, `autoflake`, `build`, `pre-commit` | Developing the package |
| `docs` | `mkdocs-material>=9.5` | Building this documentation site |

## WeasyPrint system libraries

The `reports` and `all` extras pull in [WeasyPrint](https://weasyprint.org/)
for PDF rendering. WeasyPrint depends on native libraries — principally
**Pango** and **Cairo** — that `pip` does not install. Install them through
your operating system's package manager before relying on PDF downloads, per
WeasyPrint's
[installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation).

!!! tip "PDF is the only path that needs them"
    The HTML report *preview* imports WeasyPrint lazily, so the dashboard and
    previews work even when the native libraries are absent. Only the PDF
    download and email paths require Pango and Cairo.

## Optional integrations

| Integration | Needed for |
| --- | --- |
| Django Channels | WebSocket monitoring via `WebSocketLoggingMixin` — only if your project uses Channels consumers |
| A Celery broker (Redis, RabbitMQ, …) | Running the Celery tasks and Beat schedule, rather than relying on the built-in timer |
| An SMTP server | [Emailing reports](guides/email.md) |
