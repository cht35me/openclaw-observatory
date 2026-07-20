"""Storage layer: interface plus concrete backends.

``EventStorage`` is the extension point mandated by the M002 supervisor
guidance — future backends (e.g. SQLite for the Local Observatory, SD-005)
implement the same interface without touching API code.
"""

from app.storage.base import EventStorage, StorageError
from app.storage.clickhouse import ClickHouseEventStorage
from app.storage.memory import InMemoryEventStorage

__all__ = [
    "ClickHouseEventStorage",
    "EventStorage",
    "InMemoryEventStorage",
    "StorageError",
]
