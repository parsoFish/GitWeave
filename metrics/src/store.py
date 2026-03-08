"""EventStore Protocol and in-memory implementation for GitHub webhook events.

The Protocol defines the interface that any EventStore backend must satisfy,
enabling PostgreSQL (or any other store) to be swapped in without changing
the handler code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventStore(Protocol):
    """Contract for storing and querying parsed GitHub webhook events."""

    def store_event(self, event: dict[str, Any]) -> None:
        """Persist a parsed event.

        Implementations must copy the event rather than storing a reference
        so that subsequent mutations by the caller do not corrupt stored data.
        """
        ...

    def get_events(
        self,
        repo: str,
        event_type: str,
        since_dt: datetime,
    ) -> list[dict[str, Any]]:
        """Return all events matching repo, event_type, and created_at >= since_dt.

        Returns a new list (snapshot) — callers may mutate the result without
        affecting the store's internal state.
        """
        ...


class InMemoryEventStore:
    """Thread-unsafe in-memory EventStore for development and testing.

    Suitable for single-process use. Replace with a PostgreSQL-backed
    implementation for production deployments where persistence and
    horizontal scaling are required.
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def store_event(self, event: dict[str, Any]) -> None:
        """Store a copy of the event to prevent mutation of stored data."""
        self._events.append(dict(event))

    def get_events(
        self,
        repo: str,
        event_type: str,
        since_dt: datetime,
    ) -> list[dict[str, Any]]:
        """Return a snapshot of events matching all three filter criteria."""
        return [
            dict(e)
            for e in self._events
            if e.get("repo") == repo
            and e.get("event_type") == event_type
            and e.get("created_at", datetime.min) >= since_dt
        ]
