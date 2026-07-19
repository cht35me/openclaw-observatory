"""ASGI middleware: request size limiting, request logging, HTTP metrics.

Implemented as pure ASGI middleware (not ``BaseHTTPMiddleware``) to avoid
response buffering and to work correctly with streaming bodies.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.metrics import AppMetrics

_logger = logging.getLogger("observatory.request")


class BodyTooLargeError(Exception):
    """Raised while streaming a request body that exceeds the limit."""


def _json_response_messages(status: int, body: dict[str, Any]) -> tuple[Message, Message]:
    payload = json.dumps(body).encode("utf-8")
    return (
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        },
        {"type": "http.response.body", "body": payload},
    )


class RequestSizeLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` with HTTP 413.

    Checks the ``Content-Length`` header first (cheap path), and also counts
    streamed body bytes so clients using chunked transfer cannot bypass the
    limit (security.md checklist: request size limits).
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = -1
            if declared > self.max_bytes or declared < 0:
                await self._reject(send)
                return

        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLargeError:
            if response_started:
                raise
            await self._reject(send)

    async def _reject(self, send: Send) -> None:
        start, body = _json_response_messages(
            413, {"detail": "Request body too large."}
        )
        await send(start)
        await send(body)


class RequestContextMiddleware:
    """Assign a request ID, emit one structured log line per request, and
    record HTTP metrics.

    Logged fields: ``request_id``, timestamp, ``duration_ms``, ``endpoint``,
    ``status``, and ``collector_id`` when a handler stored it on
    ``request.state`` (M002 §8). Headers and bodies are never logged.

    Metric ``path`` labels use the matched route template to keep cardinality
    bounded; unmatched paths are collapsed into ``"unmatched"``.
    """

    def __init__(self, app: ASGIApp, metrics: AppMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id

        method: str = scope["method"]
        start = time.perf_counter()
        status_code = 500  # assume the worst until a response actually starts

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            self._record(scope, method, status_code, start, request_id, failed=True)
            raise
        self._record(scope, method, status_code, start, request_id, failed=False)

    def _record(
        self,
        scope: Scope,
        method: str,
        status_code: int,
        start: float,
        request_id: str,
        failed: bool,
    ) -> None:
        duration = time.perf_counter() - start
        route = scope.get("route")
        path_label = getattr(route, "path", None) or "unmatched"
        endpoint: str = scope.get("path", path_label)
        collector_id = scope.get("state", {}).get("collector_id")

        self.metrics.http_requests_total.labels(
            method=method, path=path_label, status=str(status_code)
        ).inc()
        self.metrics.http_request_duration_seconds.labels(
            method=method, path=path_label
        ).observe(duration)

        log_extra = {
            "request_id": request_id,
            "method": method,
            "endpoint": endpoint,
            "status": status_code,
            "duration_ms": round(duration * 1000, 2),
            "collector_id": collector_id,
        }
        if failed:
            _logger.exception("request failed", extra=log_extra)
        else:
            _logger.info("request completed", extra=log_extra)
