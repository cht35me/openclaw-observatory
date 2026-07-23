"""Same-origin serving of the built frontend SPA (M004 PR3, SD-020 spirit).

The FastAPI backend mounts the Vite production build (``frontend/dist``) so
the operations console is served from the same origin as the API: zero CORS
configuration, zero new processes or ports, and the SPA inherits exactly the
backend's network exposure (loopback/tailnet only, SD-003). Full rationale
and the rejected reverse-proxy alternative: docs/frontend-architecture.md §7.

Mount design (supervisor gate requirements, binding):

* **Route precedence is preserved.** The mount is registered *after* every
  API router, and Starlette matches routes in registration order — so
  ``/api/*``, ``/health``, ``/metrics``, and ``/monitor`` always win. Only
  paths no API route claims ever reach the SPA mount.
* **No blanket SPA fallback.** A missing *file* (any path whose final
  segment has an extension, e.g. ``/assets/gone.js``) stays a hard 404 —
  a broken asset reference must fail loudly, never silently deliver
  ``index.html``. The ``index.html`` fallback applies only to extension-less
  navigation paths (``/fleet/RPSG01``, ``/settings``, …), where the client
  router owns the not-found experience.
* **Unknown ``/api/...`` paths keep the backend's own 404.** They are
  explicitly excluded from the fallback, so a typo'd endpoint returns JSON
  ``{"detail": "Not Found"}``, not a 200 with HTML.
* **The frontend is optional at runtime.** :func:`mount_frontend` is a no-op
  unless ``<dist>/index.html`` exists — the backend (and its test suite)
  runs unchanged with no built frontend present.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

_logger = logging.getLogger("observatory.spa")

#: Default location of the Vite production build, relative to the repository
#: root (backend/app/spa.py → repo root → frontend/dist).
DEFAULT_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

#: First path segments that must never fall back to the SPA (they belong to
#: the API surface; real routes already win by precedence — this guards the
#: *unknown* paths beneath them).
_RESERVED_PREFIXES = ("api",)


class SpaStaticFiles(StaticFiles):
    """StaticFiles with a deliberate, narrow SPA ``index.html`` fallback."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._is_navigation_path(path):
                raise
            return await super().get_response("index.html", scope)

    @staticmethod
    def _is_navigation_path(path: str) -> bool:
        """True only for extension-less, non-API paths (client-side routes)."""
        first_segment = path.split("/", 1)[0]
        if first_segment in _RESERVED_PREFIXES:
            return False
        final_segment = path.rsplit("/", 1)[-1]
        return "." not in final_segment


def resolve_dist_dir(configured: str) -> Path:
    """The dist directory to serve: explicit setting or the repo default."""
    return Path(configured) if configured else DEFAULT_DIST_DIR


def mount_frontend(app: FastAPI, dist_dir: Path) -> bool:
    """Mount the built SPA at ``/`` if a build exists; returns whether it did.

    Must be called *after* all API routers are registered so their routes
    keep precedence over the mount.
    """
    if not (dist_dir / "index.html").is_file():
        _logger.info("no frontend build at %s; SPA serving disabled", dist_dir)
        return False
    app.mount("/", SpaStaticFiles(directory=dist_dir, html=True), name="frontend")
    _logger.info("serving frontend SPA from %s", dist_dir)
    return True
