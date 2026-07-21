"""HTTP client for the Observatory ingestion API (stdlib only).

Submits events to ``POST /api/v1/events`` with the per-collector API key
(SD-017). Transient failures (connection errors, 5xx/503) are retried with
exponential backoff; client errors (4xx) are never retried — they indicate a
bug or misconfiguration, and retrying would only repeat the rejection.

The client counts failures (``failures_total``); the runner self-reports the
count in every heartbeat so the backend health score notices a collector
that keeps failing (M003 §9).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from observatory_collectors.config import CollectorConfig

_logger = logging.getLogger("collector.client")

#: HTTP statuses worth retrying (server-side/transient).
_RETRYABLE_STATUSES = frozenset({500, 502, 503, 504})


class SubmissionError(Exception):
    """Raised when an event could not be delivered (after retries)."""


class ObservatoryClient:
    """Minimal, dependency-free client for the ingestion API."""

    def __init__(
        self,
        config: CollectorConfig,
        sleep_fn: Callable[[float], None] = time.sleep,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self._config = config
        self._sleep = sleep_fn
        self._opener = opener
        #: Cumulative delivery/collection failures (reported in heartbeats).
        self.failures_total = 0

    def submit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        schema_version: int = 1,
        timestamp: datetime | None = None,
    ) -> bool:
        """Deliver one event; returns True on acceptance.

        Never raises on delivery failure — collectors must keep collecting
        even when the Observatory is down (failures are counted instead).
        """
        body = json.dumps(
            {
                "collector_id": self._config.fleet_id,
                "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
                "event_type": event_type,
                "schema_version": schema_version,
                "payload": payload,
            }
        ).encode("utf-8")

        delay = 1.0
        attempts = self._config.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                self._post(body)
                return True
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRYABLE_STATUSES and attempt < attempts:
                    _logger.warning(
                        "submit %s got HTTP %s; retrying in %.1fs",
                        event_type,
                        exc.code,
                        delay,
                    )
                else:
                    _logger.error(
                        "submit %s rejected with HTTP %s (no retry)",
                        event_type,
                        exc.code,
                    )
                    self.failures_total += 1
                    return False
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                if attempt >= attempts:
                    _logger.error(
                        "submit %s failed after %d attempts: %s", event_type, attempts, exc
                    )
                    self.failures_total += 1
                    return False
                _logger.warning(
                    "submit %s connection error (%s); retrying in %.1fs",
                    event_type,
                    exc,
                    delay,
                )
            self._sleep(delay)
            delay = min(delay * 2, 30.0)
        return False  # pragma: no cover - loop always returns earlier

    def _post(self, body: bytes) -> None:
        request = urllib.request.Request(
            f"{self._config.observatory_url}/api/v1/events",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self._config.api_key,
                "User-Agent": f"observatory-collector/{self._config.collector_name}",
            },
        )
        with self._opener(request, timeout=self._config.request_timeout) as response:
            # 2xx: drain and succeed; anything else raises HTTPError upstream.
            response.read()
