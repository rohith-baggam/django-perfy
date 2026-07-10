"""django-perfy — API, WebSocket and server performance monitoring for Django.

Public helpers exposed here keep host projects from hardcoding paths into the
package. Use :data:`DASHBOARD_TEMPLATES_DIR` and :data:`DASHBOARD_STATIC_DIR`
when wiring the Jinja2 template backend and ``STATICFILES_DIRS``.
"""

from __future__ import annotations

import os

__version__: str = "0.1.0"

_PACKAGE_DIR: str = os.path.dirname(os.path.abspath(__file__))

#: Directory holding the Jinja2 dashboard templates. Add to the Jinja2 template
#: backend's ``DIRS`` (see the README for the exact settings block).
DASHBOARD_TEMPLATES_DIR: str = os.path.join(_PACKAGE_DIR, "dashboard", "templates")

#: Directory holding the dashboard CSS/JS. Add to ``STATICFILES_DIRS``.
DASHBOARD_STATIC_DIR: str = os.path.join(_PACKAGE_DIR, "dashboard", "static")

__all__: list[str] = [
    "__version__",
    "DASHBOARD_TEMPLATES_DIR",
    "DASHBOARD_STATIC_DIR",
]
