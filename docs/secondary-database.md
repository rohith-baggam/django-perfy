# Storing telemetry in a secondary database

Performance telemetry can be high-volume. Keeping it out of your primary
database isolates that write load and lets you size, back up and retain the two
independently. `django-perfy` makes this a one-setting change.

## How it works

Every model in the package is registered under the `performance` app label. The
bundled `django_perfy.router.PerformanceRouter` reads
`PERFORMANCE_MONITOR["DATABASE"]` and pins **reads, writes and migrations** for
that app label to the chosen alias. The router is appended to
`DATABASE_ROUTERS` automatically when the app starts, so you don't have to
register it yourself.

When `DATABASE` is `"default"` (the out-of-the-box value) the router is a no-op
and nothing about a single-database project changes.

## Setup

### 1. Declare the alias

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "app",
        # ...
    },
    "performance": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "perf_metrics",
        "USER": "perf",
        "PASSWORD": "...",
        "HOST": "metrics-db.internal",
        "PORT": "5432",
    },
}
```

### 2. Point the app at it

```python
PERFORMANCE_MONITOR = {
    # ...
    "DATABASE": "performance",
}
```

### 3. Migrate the alias

Because the router confines the `performance` tables to their alias, run migrate
against that database explicitly:

```bash
python manage.py migrate                          # your app tables on default
python manage.py migrate --database=performance   # performance tables here
```

The `allow_migrate` rule guarantees the `performance` tables are **only** created
on the configured alias — they will not appear on `default`, and other apps'
tables will not be created on the `performance` alias by this router.

## Registering the router manually (optional)

Auto-registration covers the common case. If you prefer to be explicit — or you
manage `DATABASE_ROUTERS` yourself — add it directly; the auto-registration step
detects it and won't add a duplicate:

```python
DATABASE_ROUTERS = ["django_perfy.router.PerformanceRouter"]
```

## Operational notes

- **Backups / retention** can now differ from your primary database.
- **Cross-database relations**: performance models only relate to each other, so
  there are no cross-database foreign keys to worry about.
- **Connection pooling**: the secondary alias uses its own connection settings;
  tune `CONN_MAX_AGE` etc. independently.
- **Switching back**: set `DATABASE` to `"default"` and the router stops routing.
  (Existing rows stay in whichever database they were written to.)
