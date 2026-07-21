"""Environment-driven application configuration.

All runtime configuration comes from environment variables (or an optional
local ``.env`` file for development), per docs/deployment.md §3 and
docs/security.md §5: configuration in the repository holds placeholder
*examples* only, never real values.

Secret-bearing fields (``API_KEYS``, ``CLICKHOUSE_PASSWORD``) use
:class:`pydantic.SecretStr` so their values are never exposed through
``repr()``/``str()`` — and therefore never leak into logs or tracebacks.
"""

from __future__ import annotations

import json
from functools import cached_property

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment variables.

    Environment variable names are the upper-cased field names
    (e.g. ``clickhouse_host`` ⇒ ``CLICKHOUSE_HOST``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- ClickHouse (SD-005: central storage) ---
    clickhouse_host: str = "localhost"
    clickhouse_port: int = Field(default=8123, ge=1, le=65535)
    clickhouse_database: str = "observatory"
    clickhouse_username: str = "default"
    clickhouse_password: SecretStr = SecretStr("")
    clickhouse_connect_timeout: float = Field(default=3.0, gt=0)

    # --- Collector authentication (SD-017: key ↔ identity binding) ---
    # Each API key is bound to exactly one Fleet identity (collector_id).
    # Comma-separated `collector_id:key` pairs, or a JSON object mapping
    # collector_id to a key (or list of keys, for rotation).
    api_keys: SecretStr = SecretStr("")

    # --- Service behaviour ---
    log_level: str = "INFO"
    app_version: str = "0.1.0"
    app_name: str = "openclaw-observatory-backend"

    # Request size limit (bytes) enforced by middleware (security.md checklist).
    max_request_bytes: int = Field(default=1_048_576, gt=0)

    # --- Fleet / self-identity (M003) ---
    # The backend itself is a Fleet Registry *service* asset (FLEET.md:
    # OBLN01 = Observatory Local Node deployment 01, hosted on RPSG01); it
    # stamps its own heartbeat so the Observatory is visible in its own
    # registry.
    fleet_id: str = "OBLN01"
    collector_name: str = "observatory-backend"

    # --- Heartbeats and offline detection (M003 §5/§6) ---
    # Interval (seconds) of the backend's own heartbeat; collectors have
    # their own HEARTBEAT_INTERVAL environment variable.
    heartbeat_interval: float = Field(default=30.0, gt=0)
    # An asset whose newest heartbeat is older than this is OFFLINE.
    offline_timeout: float = Field(default=90.0, gt=0)
    # How often the offline detector scans the registry (seconds).
    offline_check_interval: float = Field(default=15.0, gt=0)
    # Master switch for background loops (offline detector, self-heartbeat).
    # Tests disable it for determinism; production keeps the default.
    background_tasks_enabled: bool = True

    # --- Health-score thresholds (M003 §9) ---
    health_cpu_temp_warning_c: float = 70.0
    health_cpu_temp_critical_c: float = 80.0
    health_disk_warning_percent: float = 80.0
    health_disk_critical_percent: float = 90.0
    health_ram_warning_percent: float = 85.0
    health_ram_critical_percent: float = 95.0
    # Heartbeat age (as a multiple of offline_timeout) that degrades health
    # to Warning before the hard offline cut-off is reached.
    health_heartbeat_warning_ratio: float = Field(default=0.5, gt=0, le=1.0)
    # A collector reporting at least this many cumulative failures is Warning.
    health_collector_failures_warning: int = Field(default=1, ge=1)

    @cached_property
    def api_key_bindings(self) -> tuple[tuple[str, str], ...]:
        """Parse ``API_KEYS`` into ``(collector_id, key)`` bindings (SD-017).

        Accepted forms:

        * comma-separated pairs — ``RPSG01:key-a,BITAXE01:key-b``;
        * JSON object — ``{"RPSG01": "key-a", "BITAXE01": ["key-b", "key-c"]}``
          (a list value allows key rotation for one identity).

        Every key is bound to exactly one collector_id; the same collector_id
        may hold several keys (rotation), but reusing one key across two
        identities is a configuration error.
        """
        raw = self.api_keys.get_secret_value().strip()
        if not raw:
            return ()
        pairs: list[tuple[str, str]] = []
        if raw.startswith("{"):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("API_KEYS looks like JSON but failed to parse") from exc
            if not isinstance(parsed, dict):
                raise ValueError("API_KEYS JSON form must be an object")
            for collector_id, value in parsed.items():
                keys = value if isinstance(value, list) else [value]
                if not all(isinstance(k, str) for k in keys):
                    raise ValueError("API_KEYS JSON values must be strings or string arrays")
                pairs.extend((collector_id.strip(), k.strip()) for k in keys)
        else:
            for entry in raw.split(","):
                entry = entry.strip()
                if not entry:
                    continue
                collector_id, sep, key = entry.partition(":")
                if not sep:
                    raise ValueError(
                        "API_KEYS entries must be `collector_id:key` pairs (SD-017); "
                        "a bare key with no identity binding is not accepted"
                    )
                pairs.append((collector_id.strip(), key.strip()))
        bindings = tuple((c, k) for c, k in pairs if c and k)
        if len(pairs) != len(bindings):
            raise ValueError("API_KEYS contains an entry with an empty collector_id or key")
        seen: dict[str, str] = {}
        for collector_id, key in bindings:
            if key in seen and seen[key] != collector_id:
                raise ValueError("API_KEYS binds one key to multiple collector identities (SD-017)")
            seen[key] = collector_id
        return bindings


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the environment."""
    return Settings()
