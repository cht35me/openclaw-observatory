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

    # --- Collector authentication ---
    # Comma-separated or JSON-array list of accepted collector API keys.
    api_keys: SecretStr = SecretStr("")

    # --- Service behaviour ---
    log_level: str = "INFO"
    app_version: str = "0.1.0"
    app_name: str = "openclaw-observatory-backend"

    # Request size limit (bytes) enforced by middleware (security.md checklist).
    max_request_bytes: int = Field(default=1_048_576, gt=0)

    @cached_property
    def api_key_list(self) -> tuple[str, ...]:
        """Parse ``API_KEYS`` into a tuple of keys.

        Accepts either a JSON array (``["key-a", "key-b"]``) or a
        comma-separated string (``key-a,key-b``). Empty entries are dropped.
        """
        raw = self.api_keys.get_secret_value().strip()
        if not raw:
            return ()
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("API_KEYS looks like JSON but failed to parse") from exc
            if not isinstance(parsed, list) or not all(isinstance(k, str) for k in parsed):
                raise ValueError("API_KEYS JSON form must be an array of strings")
            keys = [k.strip() for k in parsed]
        else:
            keys = [k.strip() for k in raw.split(",")]
        return tuple(k for k in keys if k)


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the environment."""
    return Settings()
