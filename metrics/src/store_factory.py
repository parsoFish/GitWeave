"""Factory for creating the correct EventStore implementation.

Reads the DATABASE_URL environment variable at call time:
  - Absent or whitespace-only → InMemoryEventStore (default, no external deps)
  - Set to a postgres URL      → PostgreSQLEventStore

This module is the single place where the implementation decision is made,
keeping all other code decoupled from the concrete store type.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from store import InMemoryEventStore
from store_pg import PostgreSQLEventStore

if TYPE_CHECKING:
    from store import EventStore


def create_event_store() -> "EventStore":
    """Return an EventStore appropriate for the current environment.

    Reads DATABASE_URL at call time so tests can patch os.environ without
    needing to reload this module.

    Returns:
        InMemoryEventStore when DATABASE_URL is absent or empty.
        PostgreSQLEventStore when DATABASE_URL is set to a non-empty string.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgreSQLEventStore(database_url)
    return InMemoryEventStore()
