"""Health score unit tests (M003 §9)."""

from __future__ import annotations

from app.config import Settings
from app.models.registry import Connectivity, HealthStatus
from app.services.health import compute_health

SETTINGS = Settings(
    _env_file=None,
    api_keys="RPSG01:k1",
    offline_timeout=60.0,
)


def _score(
    connectivity=Connectivity.ONLINE,
    heartbeat_age=5.0,
    payload=None,
    failures=0,
) -> HealthStatus:
    return compute_health(
        SETTINGS,
        connectivity=connectivity,
        heartbeat_age_seconds=heartbeat_age,
        system_payload=payload,
        collector_failures=failures,
    )


def _payload(temp=45.0, disk=40.0, ram=50.0) -> dict:
    return {
        "cpu": {"temperature_c": temp},
        "disk": {"used_percent": disk},
        "memory": {"used_percent": ram},
    }


def test_offline_and_unknown_short_circuit() -> None:
    assert _score(connectivity=Connectivity.OFFLINE) is HealthStatus.OFFLINE
    assert _score(connectivity=Connectivity.UNKNOWN) is HealthStatus.UNKNOWN


def test_healthy_with_nominal_signals() -> None:
    assert _score(payload=_payload()) is HealthStatus.HEALTHY


def test_no_telemetry_is_still_healthy_when_heartbeating() -> None:
    """Missing signals are not penalized (agent collectors have no CPU temp)."""
    assert _score(payload=None) is HealthStatus.HEALTHY


def test_warning_thresholds() -> None:
    assert _score(payload=_payload(temp=72.0)) is HealthStatus.WARNING
    assert _score(payload=_payload(disk=85.0)) is HealthStatus.WARNING
    assert _score(payload=_payload(ram=90.0)) is HealthStatus.WARNING
    # Stale-ish heartbeat (over half of offline_timeout) degrades early.
    assert _score(heartbeat_age=45.0, payload=_payload()) is HealthStatus.WARNING
    # Collector self-reported failures degrade the score.
    assert _score(payload=_payload(), failures=3) is HealthStatus.WARNING


def test_critical_thresholds_dominate() -> None:
    assert _score(payload=_payload(temp=85.0)) is HealthStatus.CRITICAL
    assert _score(payload=_payload(disk=95.0)) is HealthStatus.CRITICAL
    assert _score(payload=_payload(ram=97.0)) is HealthStatus.CRITICAL
    # Critical wins even when other signals only warn.
    assert _score(payload=_payload(temp=85.0, disk=85.0)) is HealthStatus.CRITICAL


def test_malformed_telemetry_is_ignored() -> None:
    """Health scoring is defensive: junk payloads never crash or mislead."""
    junk = {"cpu": "hot", "disk": {"used_percent": "full"}, "memory": []}
    assert _score(payload=junk) is HealthStatus.HEALTHY
