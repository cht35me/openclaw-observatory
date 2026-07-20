"""Offline detection tests (M003 §6): transition events, recovery, gauges."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.config import Settings
from app.metrics import AppMetrics
from app.models.event import Event
from app.services.offline import BackendHeartbeat, OfflineDetector
from app.services.seed import SEED_ASSETS, seed_registry
from app.storage.memory import InMemoryEventStorage, InMemoryRegistryStorage

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        api_keys="RPSG01:k1",
        offline_timeout=60.0,
        background_tasks_enabled=False,
        **overrides,
    )


def _heartbeat_event(collector_id: str, timestamp: datetime) -> Event:
    return Event(
        id=uuid4(),
        collector_id=collector_id,
        timestamp=timestamp,
        event_type="heartbeat",
        payload={"collector_type": "raspberry", "collector_version": "1.0.0"},
        schema_version=1,
        received_at=timestamp,
    )


def _detector(now: datetime):
    settings = _settings()
    events = InMemoryEventStorage()
    registry = InMemoryRegistryStorage()
    metrics = AppMetrics.create(version="test")
    clock = {"now": now}
    detector = OfflineDetector(
        settings, registry, events, metrics, now_fn=lambda: clock["now"]
    )
    return detector, events, registry, metrics, clock


async def _events_of_type(events: InMemoryEventStorage, event_type: str) -> list[Event]:
    return await events.query_events(event_type=event_type, limit=100)


def test_stopping_collector_generates_offline_event() -> None:
    async def scenario() -> None:
        detector, events, registry, metrics, clock = _detector(NOW)
        await seed_registry(registry, now_fn=lambda: NOW)
        await events.insert_event(_heartbeat_event("RPSG01", NOW))

        # First sweep: RPSG01 online, baseline set, no transitions.
        await detector.run_once()
        assert await _events_of_type(events, "asset_offline") == []

        # Collector goes silent past OFFLINE_TIMEOUT.
        clock["now"] = NOW + timedelta(seconds=120)
        await detector.run_once()

        offline = await _events_of_type(events, "asset_offline")
        assert len(offline) == 1
        assert offline[0].collector_id == "RPSG01"
        assert offline[0].payload["previous"] == "online"
        assert offline[0].payload["current"] == "offline"
        assert offline[0].payload["detected_by"] == "OBLN01"

        # Sweep again: still offline, but no duplicate event.
        clock["now"] = NOW + timedelta(seconds=180)
        await detector.run_once()
        assert len(await _events_of_type(events, "asset_offline")) == 1

    asyncio.run(scenario())


def test_restarting_collector_generates_online_recovery_event() -> None:
    async def scenario() -> None:
        detector, events, registry, metrics, clock = _detector(NOW)
        await seed_registry(registry, now_fn=lambda: NOW)
        await events.insert_event(_heartbeat_event("RPSG01", NOW))

        await detector.run_once()  # baseline: online
        clock["now"] = NOW + timedelta(seconds=120)
        await detector.run_once()  # offline

        # Collector restarts and heartbeats again.
        clock["now"] = NOW + timedelta(seconds=150)
        await events.insert_event(_heartbeat_event("RPSG01", clock["now"]))
        await detector.run_once()

        online = await _events_of_type(events, "asset_online")
        assert len(online) == 1
        assert online[0].collector_id == "RPSG01"
        assert online[0].payload["previous"] == "offline"

        registry_metrics = metrics.registry
        assert registry_metrics.get_sample_value(
            "observatory_offline_transitions_total",
            {"collector_id": "RPSG01", "direction": "offline"},
        ) == 1.0
        assert registry_metrics.get_sample_value(
            "observatory_offline_transitions_total",
            {"collector_id": "RPSG01", "direction": "online"},
        ) == 1.0

    asyncio.run(scenario())


def test_never_seen_assets_count_as_unknown_without_events() -> None:
    """Freshly seeded assets produce gauge visibility, not an OFFLINE storm."""

    async def scenario() -> None:
        detector, events, registry, metrics, clock = _detector(NOW)
        await seed_registry(registry, now_fn=lambda: NOW)

        await detector.run_once()
        await detector.run_once()

        assert await _events_of_type(events, "asset_offline") == []
        registry_metrics = metrics.registry
        assert registry_metrics.get_sample_value(
            "observatory_fleet_registered_assets", {}
        ) == float(len(SEED_ASSETS))
        assert registry_metrics.get_sample_value(
            "observatory_fleet_unknown_assets", {}
        ) == float(len(SEED_ASSETS))
        assert registry_metrics.get_sample_value(
            "observatory_fleet_active_assets", {}
        ) == 0.0

    asyncio.run(scenario())


def test_gauges_reflect_mixed_connectivity() -> None:
    async def scenario() -> None:
        detector, events, registry, metrics, clock = _detector(NOW)
        await seed_registry(registry, now_fn=lambda: NOW)
        # RPSG01 fresh, A001 stale, OBLN01 never seen.
        await events.insert_event(_heartbeat_event("RPSG01", NOW))
        await events.insert_event(
            _heartbeat_event("A001", NOW - timedelta(seconds=600))
        )

        await detector.run_once()

        registry_metrics = metrics.registry
        assert registry_metrics.get_sample_value(
            "observatory_fleet_active_assets", {}
        ) == 1.0
        assert registry_metrics.get_sample_value(
            "observatory_fleet_offline_assets", {}
        ) == 1.0
        assert registry_metrics.get_sample_value(
            "observatory_fleet_unknown_assets", {}
        ) == 1.0

    asyncio.run(scenario())


def test_backend_self_heartbeat() -> None:
    """OBLN01 stamps its own heartbeat so the Observatory monitors itself."""

    async def scenario() -> None:
        settings = _settings()
        events = InMemoryEventStorage()
        beat = BackendHeartbeat(
            settings, events, uptime_fn=lambda: 42.0, now_fn=lambda: NOW
        )
        event = await beat.beat_once()
        assert event.collector_id == "OBLN01"
        assert event.event_type == "heartbeat"
        assert event.payload["collector_type"] == "observatory-backend"
        assert event.payload["uptime_seconds"] == 42.0
        stored = await events.query_events(collector_id="OBLN01", limit=10)
        assert len(stored) == 1

    asyncio.run(scenario())
