"""Dependency-injection helpers.

Application-scoped objects (settings, storage, metrics, authenticator) are
constructed once in the app factory and stored on ``app.state``; these
dependencies fetch them per-request. Tests override behaviour by passing
alternative implementations to :func:`app.main.create_app` — no monkeypatching
of module globals required.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.metrics import AppMetrics
from app.storage.base import EventStorage


def get_settings(request: Request) -> Settings:
    """Return the application settings."""
    return request.app.state.settings


def get_storage(request: Request) -> EventStorage:
    """Return the configured event-storage backend."""
    return request.app.state.storage


def get_metrics(request: Request) -> AppMetrics:
    """Return the application metrics container."""
    return request.app.state.metrics


SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[EventStorage, Depends(get_storage)]
MetricsDep = Annotated[AppMetrics, Depends(get_metrics)]
