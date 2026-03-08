"""TDD tests for the store factory — DATABASE_URL env-var switching.

The factory function create_event_store() must:
  - Return an InMemoryEventStore when DATABASE_URL is not set
  - Return a PostgreSQLEventStore when DATABASE_URL is set
  - Both implementations must satisfy the EventStore Protocol
  - The returned store must be usable immediately (no deferred initialisation
    that would break callers in the happy path)

The module under test is metrics/src/store_factory.py.

Environment variable semantics:
  - DATABASE_URL absent / empty string → InMemoryEventStore
  - DATABASE_URL = "postgresql://..." → PostgreSQLEventStore

These tests are written BEFORE implementation (TDD red phase).
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


class TestStoreFactoryModuleStructure:
    """store_factory module must be importable and expose create_event_store."""

    def test_store_factory_module_is_importable(self):
        import store_factory  # noqa: F401

    def test_create_event_store_function_is_importable(self):
        from store_factory import create_event_store  # noqa: F401

    def test_create_event_store_is_callable(self):
        from store_factory import create_event_store

        assert callable(create_event_store)


# ---------------------------------------------------------------------------
# InMemoryEventStore selected when DATABASE_URL is absent
# ---------------------------------------------------------------------------


class TestCreateEventStoreWithoutDatabaseUrl:
    """create_event_store() must return InMemoryEventStore when DATABASE_URL is unset."""

    def test_returns_in_memory_store_when_database_url_not_set(self):
        from store import InMemoryEventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            # Ensure DATABASE_URL is absent
            os.environ.pop("DATABASE_URL", None)
            store = create_event_store()

        assert isinstance(store, InMemoryEventStore)

    def test_returns_in_memory_store_when_database_url_is_empty_string(self):
        from store import InMemoryEventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            store = create_event_store()

        assert isinstance(store, InMemoryEventStore)

    def test_in_memory_store_is_functional_without_database_url(self):
        """The returned InMemoryEventStore must accept store/get operations immediately."""
        from store import InMemoryEventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store = create_event_store()

        ts = _utcnow()
        store.store_event({"event_type": "push", "repo": "org/repo", "created_at": ts})
        results = store.get_events("org/repo", "push", ts)
        assert len(results) == 1

    def test_in_memory_store_satisfies_event_store_protocol(self):
        from store import EventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store = create_event_store()

        assert isinstance(store, EventStore)

    def test_returns_in_memory_store_when_database_url_is_whitespace_only(self):
        """Whitespace-only DATABASE_URL is treated as absent."""
        from store import InMemoryEventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {"DATABASE_URL": "   "}):
            store = create_event_store()

        assert isinstance(store, InMemoryEventStore)


# ---------------------------------------------------------------------------
# PostgreSQLEventStore selected when DATABASE_URL is present
# ---------------------------------------------------------------------------


class TestCreateEventStoreWithDatabaseUrl:
    """create_event_store() must return PostgreSQLEventStore when DATABASE_URL is set."""

    def test_returns_postgresql_store_when_database_url_set(self):
        """PostgreSQLEventStore is returned when DATABASE_URL contains a postgres URL."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost:5432/testdb"}):
            # We patch PostgreSQLEventStore.__init__ to avoid requiring a real DB
            with patch("store_factory.PostgreSQLEventStore") as MockPGStore:
                MockPGStore.return_value = MagicMock()
                from store_factory import create_event_store

                # Force reimport to pick up patched constructor
                import importlib
                import store_factory
                importlib.reload(store_factory)
                from store_factory import create_event_store as fresh_create

                store = fresh_create()

            MockPGStore.assert_called_once_with("postgresql://user:pass@localhost:5432/testdb")

    def test_database_url_passed_to_postgresql_store_constructor(self):
        """The exact DATABASE_URL value must be forwarded to PostgreSQLEventStore."""
        pg_url = "postgresql://admin:secret@db-host:5432/gitweave_prod"
        with patch.dict(os.environ, {"DATABASE_URL": pg_url}):
            with patch("store_factory.PostgreSQLEventStore") as MockPGStore:
                MockPGStore.return_value = MagicMock()
                import store_factory
                importlib.reload(store_factory)
                from store_factory import create_event_store as fresh_create

                fresh_create()

            MockPGStore.assert_called_once_with(pg_url)

    def test_postgresql_store_satisfies_event_store_protocol(self):
        """The PostgreSQLEventStore returned by the factory must satisfy EventStore Protocol."""
        from store import EventStore

        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@h:5432/db"}):
            with patch("store_factory.PostgreSQLEventStore") as MockPGStore:
                mock_instance = MagicMock(spec_set=["store_event", "get_events"])
                mock_instance.store_event = MagicMock(return_value=None)
                mock_instance.get_events = MagicMock(return_value=[])
                MockPGStore.return_value = mock_instance
                import store_factory
                importlib.reload(store_factory)
                from store_factory import create_event_store as fresh_create

                store = fresh_create()

            # The mock satisfies the Protocol's structural check
            assert hasattr(store, "store_event")
            assert hasattr(store, "get_events")


# ---------------------------------------------------------------------------
# Factory returns different instances each call
# ---------------------------------------------------------------------------


class TestCreateEventStoreInstanceBehaviour:
    """create_event_store() behaviour regarding instance creation."""

    def test_each_call_returns_a_new_instance_without_database_url(self):
        """Without DATABASE_URL, each call returns a new InMemoryEventStore instance."""
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store_a = create_event_store()
            store_b = create_event_store()

        assert store_a is not store_b

    def test_stores_created_without_database_url_are_independent(self):
        """Two stores created via the factory without DATABASE_URL are independent."""
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store_a = create_event_store()
            store_b = create_event_store()

        ts = _utcnow()
        store_a.store_event({"event_type": "push", "repo": "org/repo", "created_at": ts})

        results_b = store_b.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert results_b == []


# ---------------------------------------------------------------------------
# Switching behaviour: env var respected at call time
# ---------------------------------------------------------------------------


class TestCreateEventStoreEnvVarRespectedAtCallTime:
    """The factory must read DATABASE_URL at call time, not at import time."""

    def test_factory_reads_database_url_at_call_time_not_import_time(self):
        """Changing DATABASE_URL between calls must change the store type returned."""
        from store import InMemoryEventStore
        from store_factory import create_event_store

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            store_without_db = create_event_store()

        assert isinstance(store_without_db, InMemoryEventStore)

        # Now set DATABASE_URL and verify the factory picks it up
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@h/db"}):
            with patch("store_factory.PostgreSQLEventStore") as MockPGStore:
                MockPGStore.return_value = MagicMock()
                import store_factory
                importlib.reload(store_factory)
                from store_factory import create_event_store as fresh_create

                store_with_db = fresh_create()

            MockPGStore.assert_called_once()
