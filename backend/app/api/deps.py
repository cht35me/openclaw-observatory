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
from app.services.pipeline import EventPipeline
from app.services.registry import RegistryService
from app.storage.base import EventStorage, HostInventoryStorage, MissionStorage


def get_settings(request: Request) -> Settings:
    """Return the application settings."""
    return request.app.state.settings


def get_storage(request: Request) -> EventStorage:
    """Return the configured event-storage backend."""
    return request.app.state.storage


def get_metrics(request: Request) -> AppMetrics:
    """Return the application metrics container."""
    return request.app.state.metrics


def get_registry_service(request: Request) -> RegistryService:
    """Return the Fleet Registry read-model service."""
    return request.app.state.registry_service


def get_mission_storage(request: Request) -> MissionStorage:
    """Return the mission projection storage backend."""
    return request.app.state.mission_storage


def get_inventory_storage(request: Request) -> HostInventoryStorage:
    """Return the Host Inventory projection storage backend (M003.5 §3)."""
    return request.app.state.inventory_storage


def get_pipeline(request: Request) -> EventPipeline:
    """Return the per-event-type ingestion pipeline."""
    return request.app.state.pipeline


SettingsDep = Annotated[Settings, Depends(get_settings)]
StorageDep = Annotated[EventStorage, Depends(get_storage)]
MetricsDep = Annotated[AppMetrics, Depends(get_metrics)]
RegistryServiceDep = Annotated[RegistryService, Depends(get_registry_service)]
MissionStorageDep = Annotated[MissionStorage, Depends(get_mission_storage)]
InventoryStorageDep = Annotated[HostInventoryStorage, Depends(get_inventory_storage)]
PipelineDep = Annotated[EventPipeline, Depends(get_pipeline)]
