"""PostgreSQL-backed EventStore implementation.

Uses SQLAlchemy Core (synchronous) with separate tables per event type:
  - push_events
  - pr_events
  - deployment_events

Alembic manages schema migrations. Call apply_migrations(database_url) before
creating a PostgreSQLEventStore instance in production.

The module also exposes apply_migrations() as a public function so the
integration test fixture can run migrations without duplicating the logic.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)

from store import EventStore

# Shared metadata object — tables are defined once and shared across instances.
_metadata = MetaData()

_push_events = Table(
    "push_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("repo", String(255), nullable=False, index=True),
    Column("ref", String(255), nullable=False, default=""),
    Column("commits", Text, nullable=False, default="[]"),
    Column("extra", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

_deployment_events = Table(
    "deployment_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("repo", String(255), nullable=False, index=True),
    Column("state", String(64), nullable=False),
    Column("environment", String(128), nullable=False),
    Column("deployment_id", BigInteger, nullable=True),
    Column("extra", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

_pr_events = Table(
    "pr_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("repo", String(255), nullable=False, index=True),
    Column("pr_number", Integer, nullable=True),
    Column("commit_sha", String(255), nullable=True),
    Column("merged_at", DateTime(timezone=True), nullable=True),
    Column("extra", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

# Mapping from event_type string to (table, fixed_columns, extra_whitelist)
_TABLE_MAP: dict[str, Table] = {
    "push": _push_events,
    "deployment_status": _deployment_events,
    "pull_request": _pr_events,
}

# Columns that are stored in dedicated table columns (not JSON extra blob)
_KNOWN_COLUMNS: dict[str, frozenset[str]] = {
    "push": frozenset({"repo", "ref", "commits", "created_at"}),
    "deployment_status": frozenset({"repo", "state", "environment", "deployment_id", "created_at"}),
    "pull_request": frozenset({"repo", "pr_number", "commit_sha", "merged_at", "created_at"}),
}


class PostgreSQLEventStore:
    """Persistent EventStore backed by PostgreSQL.

    Implements the same EventStore Protocol as InMemoryEventStore. All three
    event types (push, deployment_status, pull_request) are stored in separate
    tables so queries are table-scanned only against the relevant table.

    Extra fields not part of the table schema are serialised into a JSON
    ``extra`` column and merged back on read so the round-trip is transparent.

    Args:
        database_url: SQLAlchemy-compatible PostgreSQL DSN, e.g.
                      ``postgresql://user:pass@host:5432/dbname``.
    """

    def __init__(self, database_url: str) -> None:
        self._engine = create_engine(database_url, future=True)

    def store_event(self, event: dict[str, Any]) -> None:
        """Persist a copy of the event to the appropriate table."""
        # Work on a copy so callers cannot mutate what we store.
        event = dict(event)
        event_type = event.get("event_type")

        table = _TABLE_MAP.get(event_type)  # type: ignore[arg-type]
        if table is None:
            return  # Unknown event type — silently ignore (matches InMemory behaviour)

        known = _KNOWN_COLUMNS[event_type]  # type: ignore[index]
        row = {k: v for k, v in event.items() if k in known}

        extra_fields = {k: v for k, v in event.items() if k not in known and k != "event_type"}
        if extra_fields:
            row["extra"] = _to_json(extra_fields)
        else:
            row["extra"] = None

        # Serialise commits list for push events
        if event_type == "push" and "commits" in row:
            row["commits"] = _to_json(row["commits"])

        with self._engine.begin() as conn:
            conn.execute(table.insert().values(**row))

    def get_events(
        self,
        repo: str,
        event_type: str,
        since_dt: datetime,
    ) -> list[dict[str, Any]]:
        """Return snapshot of events matching repo, event_type, and created_at >= since_dt."""
        table = _TABLE_MAP.get(event_type)
        if table is None:
            return []

        stmt = (
            sa.select(table)
            .where(table.c.repo == repo)
            .where(table.c.created_at >= since_dt)
            .order_by(table.c.created_at)
        )

        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        return [_row_to_event(dict(row), event_type) for row in rows]

    def clear_all_events(self) -> None:
        """Delete all rows from all event tables. Test-support method only."""
        with self._engine.begin() as conn:
            for table in (_push_events, _deployment_events, _pr_events):
                conn.execute(table.delete())


def apply_migrations(database_url: str) -> None:
    """Run Alembic migrations against the given database URL.

    Idempotent: safe to call multiple times. If the Alembic migration directory
    exists, uses Alembic; otherwise falls back to SQLAlchemy create_all so the
    module works without the full Alembic setup (e.g. during unit tests that
    import this module but don't need migrations).
    """
    migrations_dir = Path(__file__).parent.parent / "migrations"

    if migrations_dir.exists():
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config()
        alembic_cfg.set_main_option("script_location", str(migrations_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(alembic_cfg, "head")
    else:
        # Fallback: create tables directly (development without full Alembic setup)
        engine = create_engine(database_url, future=True)
        _metadata.create_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Internal serialisation helpers
# ---------------------------------------------------------------------------


def _to_json(value: Any) -> str:
    """Serialise a value to JSON, converting datetime objects to ISO strings."""
    return json.dumps(value, default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _row_to_event(row: dict[str, Any], event_type: str) -> dict[str, Any]:
    """Convert a raw database row dict into the public event dict format."""
    result: dict[str, Any] = {"event_type": event_type}

    for k, v in row.items():
        if k in ("id", "extra"):
            continue
        if isinstance(v, datetime) and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        result[k] = v

    # Deserialise commits JSON for push events
    if event_type == "push" and "commits" in result:
        raw_commits = result["commits"]
        if isinstance(raw_commits, str):
            result["commits"] = json.loads(raw_commits)

    # Merge extra JSON fields back into the event dict
    extra_json = row.get("extra")
    if extra_json:
        extra = json.loads(extra_json)
        result.update(extra)

    return result
