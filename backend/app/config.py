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

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.registry import Environment

#: Placeholder marker used by every committed ``*.example`` file. A live
#: deployment that still carries it has skipped the "edit the config" step,
#: so startup validation rejects it (docs/deployment.md §12).
PLACEHOLDER_MARKER = "change-me"

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class ConfigurationError(RuntimeError):
    """Startup configuration is missing or invalid (fail fast, M003.5 §2).

    Raised by :func:`load_settings` before the server binds its socket so a
    misconfigured deployment dies with one clear, secret-free message instead
    of serving requests it cannot authenticate or store.
    """


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

    # --- Deployment identity (M003.5 §3e/§6) ---
    # Environment classification of THIS deployment, shown on the monitor
    # and part of the build/release metadata. Defaults to Development so
    # "Production" is always an explicit operator statement.
    deployment_environment: Environment = Environment.DEVELOPMENT

    # --- Monitor display timezone (M003.6 §3) ---
    # IANA name (e.g. "Asia/Singapore") for wall-clock values on /monitor
    # ("Last reboot"). Empty = the host's local timezone (/etc/localtime,
    # honouring TZ). Internal timestamps and the "generated … UTC" footer
    # stay UTC; an invalid name falls back safely (never breaks the page).
    display_tz: str = ""

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

    # --- Frontend SPA serving (M004 PR3, app/spa.py) ---
    # Directory holding the Vite production build. Empty = the repository
    # default (frontend/dist next to backend/). Serving is conditional on
    # <dir>/index.html existing — a deployment without a built frontend runs
    # exactly as before (the mount simply never happens).
    frontend_dist_dir: str = ""

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

    def startup_problems(self) -> list[str]:
        """Validate operational invariants beyond field-level type checks.

        Returns human-readable problems (never secret values). Empty list
        means the configuration is safe to serve with. Called on the
        production startup path (:func:`load_settings`); tests that build
        :class:`Settings` directly may bypass it deliberately (e.g. the
        empty-API_KEYS auth test).
        """
        problems: list[str] = []

        bindings: tuple[tuple[str, str], ...] = ()
        try:
            bindings = self.api_key_bindings
        except ValueError as exc:
            problems.append(f"API_KEYS is invalid: {exc}")
        else:
            if not bindings:
                problems.append(
                    "API_KEYS is required: no collector could authenticate. Set at least "
                    "one `collector_id:key` binding in the backend env file (SD-017)."
                )
        if any(PLACEHOLDER_MARKER in key for _, key in bindings):
            problems.append(
                "API_KEYS still contains a placeholder value from deploy/backend.example.env; "
                "generate real keys with `openssl rand -hex 32` and edit the env file."
            )

        if self.log_level.upper() not in _VALID_LOG_LEVELS:
            problems.append(
                f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}, got {self.log_level!r}"
            )

        if self.offline_timeout <= self.heartbeat_interval:
            problems.append(
                "OFFLINE_TIMEOUT must exceed HEARTBEAT_INTERVAL "
                f"({self.offline_timeout} <= {self.heartbeat_interval}): the backend would "
                "mark every asset offline between its own heartbeats."
            )

        return problems


def _format_validation_error(exc: ValidationError) -> str:
    """Render pydantic field errors as env-var-named bullets (no values)."""
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        field = "".join(str(part) for part in error["loc"]) or "<settings>"
        lines.append(f"  - {field.upper()}: {error['msg']}")
    return "\n".join(lines)


def load_settings() -> Settings:
    """Build and validate :class:`Settings` from the environment.

    Fail-fast contract (M003.5 §2): any missing or invalid configuration
    raises :class:`ConfigurationError` with a clear, secret-free message
    *before* the application starts serving. ``uvicorn --factory
    app.main:build_app`` therefore exits non-zero on bad config instead of
    binding the port.
    """
    try:
        settings = Settings()
    except ValidationError as exc:
        raise ConfigurationError(
            "invalid environment configuration:\n" + _format_validation_error(exc)
        ) from None
    problems = settings.startup_problems()
    if problems:
        raise ConfigurationError(
            "invalid environment configuration:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )
    return settings
