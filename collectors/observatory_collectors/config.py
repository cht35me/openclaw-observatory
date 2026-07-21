"""Collector configuration from environment variables (Mission M003 §8).

Secrets follow docs/security.md §5: the API key comes from
``OBSERVATORY_API_KEY`` or — preferred for systemd units — from a
tight-permission file referenced by ``OBSERVATORY_API_KEY_FILE``. Committed
configuration (``config.example.env``) holds placeholders only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _float_env(env: dict[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


@dataclass(frozen=True)
class CollectorConfig:
    """Runtime configuration shared by all collectors."""

    observatory_url: str
    api_key: str
    fleet_id: str
    collector_name: str
    heartbeat_interval: float
    telemetry_interval: float
    mission_poll_interval: float
    request_timeout: float
    max_retries: int

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        default_collector_name: str = "collector",
    ) -> CollectorConfig:
        env = dict(os.environ) if env is None else env

        api_key = env.get("OBSERVATORY_API_KEY", "").strip()
        key_file = env.get("OBSERVATORY_API_KEY_FILE", "").strip()
        if not api_key and key_file:
            try:
                api_key = Path(key_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigError(
                    f"cannot read OBSERVATORY_API_KEY_FILE {key_file!r}"
                ) from exc
        if not api_key:
            raise ConfigError(
                "OBSERVATORY_API_KEY (or OBSERVATORY_API_KEY_FILE) is required"
            )

        fleet_id = env.get("FLEET_ID", "").strip()
        if not fleet_id:
            raise ConfigError("FLEET_ID is required (the collector's Fleet identity)")

        url = env.get("OBSERVATORY_URL", "http://127.0.0.1:8000").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"OBSERVATORY_URL must be http(s), got {url!r}")

        heartbeat_interval = _float_env(env, "HEARTBEAT_INTERVAL", 30.0)
        return cls(
            observatory_url=url,
            api_key=api_key,
            fleet_id=fleet_id,
            collector_name=env.get("COLLECTOR_NAME", "").strip()
            or default_collector_name,
            heartbeat_interval=heartbeat_interval,
            telemetry_interval=_float_env(
                env, "TELEMETRY_INTERVAL", heartbeat_interval
            ),
            mission_poll_interval=_float_env(env, "MISSION_POLL_INTERVAL", 60.0),
            request_timeout=_float_env(env, "REQUEST_TIMEOUT", 10.0),
            max_retries=int(_float_env(env, "MAX_RETRIES", 3.0)),
        )
