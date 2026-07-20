"""Collector authentication.

Mission M002 implements API-key authentication for collectors. The design is
deliberately split into:

* :class:`CollectorPrincipal` — what a successful authentication yields;
* :class:`CollectorAuthenticator` — the pluggable verification strategy;
* :func:`require_collector` — the FastAPI dependency used by protected routes.

Routes depend only on ``require_collector`` and receive a principal, so a
future JWT authenticator (out of scope for M002) can replace
:class:`ApiKeyAuthenticator` without touching any endpoint code — only the
authenticator wired into ``app.state`` changes.

Identity binding (SD-017): every API key is bound to exactly one Fleet
identity, so a successful authentication yields the ``collector_id`` the key
belongs to. Ingestion routes reject events whose ``collector_id`` does not
match the authenticated identity — collectors cannot spoof each other.

Security notes (docs/security.md):

* Key comparison uses :func:`hmac.compare_digest` and evaluates *every*
  configured key without early exit, so timing does not reveal which (if any)
  key prefix-matched.
* Keys are read from the ``API_KEYS`` environment variable and are never
  logged or echoed in responses.
"""

from __future__ import annotations

import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

#: Header collectors use to present their key.
API_KEY_HEADER_NAME = "X-API-Key"

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER_NAME,
    auto_error=False,
    scheme_name="CollectorApiKey",
    description=(
        "Per-collector API key, bound to exactly one collector identity "
        "(configured via the API_KEYS environment variable, SD-017)."
    ),
)


@dataclass(frozen=True)
class CollectorPrincipal:
    """Result of a successful collector authentication.

    ``method`` records how the caller authenticated ("api_key" today, "jwt"
    later). ``subject`` is the Fleet identity (``collector_id``) the
    credential is bound to (SD-017) — the only identity this caller may
    submit telemetry for.
    """

    method: str
    subject: str


class CollectorAuthenticator(ABC):
    """Strategy interface for verifying collector credentials.

    Extension point: implement this class (e.g. ``JwtAuthenticator``) and
    assign it to ``app.state.authenticator`` to change the auth scheme without
    modifying routes.
    """

    @abstractmethod
    def authenticate(self, credential: str | None) -> CollectorPrincipal | None:
        """Return a principal if ``credential`` is valid, else ``None``."""


class ApiKeyAuthenticator(CollectorAuthenticator):
    """Validates a presented key against configured key→identity bindings.

    Constructed from ``(collector_id, key)`` pairs (SD-017): each key belongs
    to exactly one Fleet identity, and a match yields a principal whose
    ``subject`` is that identity.
    """

    def __init__(self, bindings: tuple[tuple[str, str], ...]) -> None:
        self._bindings = tuple(
            (collector_id, key.encode("utf-8")) for collector_id, key in bindings
        )

    def authenticate(self, credential: str | None) -> CollectorPrincipal | None:
        if not credential or not self._bindings:
            return None
        candidate = credential.encode("utf-8")
        # Constant-time check of every configured key; no early exit.
        matched: str | None = None
        for collector_id, key in self._bindings:
            if hmac.compare_digest(candidate, key):
                matched = collector_id
        if matched is None:
            return None
        return CollectorPrincipal(method="api_key", subject=matched)


def require_collector(
    request: Request,
    api_key: Annotated[str | None, Depends(_api_key_header)],
) -> CollectorPrincipal:
    """FastAPI dependency: reject the request unless a collector credential is valid.

    Raises ``401`` for missing or invalid credentials. The response never
    distinguishes the two cases, to avoid leaking key-validity information.
    """
    authenticator: CollectorAuthenticator = request.app.state.authenticator
    principal = authenticator.authenticate(api_key)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return principal
