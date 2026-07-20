"""Prometheus metrics endpoint (``GET /metrics``).

Exposes the per-application registry in the Prometheus text format.
Exposure model: like ``/health``, this endpoint is served without API-key
auth for scraper compatibility, and the service is only reachable over the
private tailnet (SD-003, security.md §6). See backend/OPEN_QUESTIONS.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import MetricsDep

router = APIRouter()


@router.get("/metrics", tags=["operations"])
async def metrics(app_metrics: MetricsDep) -> Response:
    """Render all application metrics in Prometheus text format."""
    return Response(
        content=generate_latest(app_metrics.registry),
        media_type=CONTENT_TYPE_LATEST,
    )
