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
    description="Per-collector API key (configured via the API_KEYS environment variable).",
)


@dataclass(frozen=True)
class CollectorPrincipal:
    """Result of a successful collector authentication.

    ``method`` records how the caller authenticated ("api_key" today, "jwt"
    later). ``subject`` is a stable identifier for the authenticated party;
    plain API keys carry no identity, so it is a fixed marker for now.
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
    """Validates a presented key against the configured key set."""

    def __init__(self, api_keys: tuple[str, ...]) -> None:
        self._keys = tuple(key.encode("utf-8") for key in api_keys)

    def authenticate(self, credential: str | None) -> CollectorPrincipal | None:
        if not credential or not self._keys:
            return None
        candidate = credential.encode("utf-8")
        # Constant-time check of every configured key; no early exit.
        valid = False
        for key in self._keys:
            valid |= hmac.compare_digest(candidate, key)
        if not valid:
            return None
        return CollectorPrincipal(method="api_key", subject="collector")


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
