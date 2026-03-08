"""Integration tests for PostgreSQLEventStore against a real Postgres instance.

These tests require a running PostgreSQL database. They are gated by the
TEST_DATABASE_URL environment variable:

  export TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test_gitweave

If TEST_DATABASE_URL is not set, all tests in this module are skipped.
In CI, a postgres service container is started and TEST_DATABASE_URL is set
via the workflow environment.

The PostgreSQLEventStore must:
  - Implement the EventStore Protocol identically to InMemoryEventStore
  - Persist events across store instance lifecycles (data survives restart)
  - Run Alembic migrations on first use (via apply_migrations())
  - Store events in separate tables: deployment_events, pr_events, push_events
  - Filter by repo, event_type, and since_dt correctly
  - Return snapshot copies (not mutable references to internal state)
  - Store copies of events (not references to the caller's dict)

The module under test is metrics/src/store_pg.py.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

# ---------------------------------------------------------------------------
# Skip entire module when TEST_DATABASE_URL is absent
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is not set — skipping PostgreSQL integration tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _push_event(
    repo: str = "org/repo",
    created_at: datetime | None = None,
    ref: str = "refs/heads/main",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "event_type": "push",
        "repo": repo,
        "ref": ref,
        "commits": [],
        "created_at": created_at or _utcnow(),
        **extra,
    }


def _deployment_event(
    repo: str = "org/repo",
    state: str = "success",
    environment: str = "production",
    created_at: datetime | None = None,
    deployment_id: int = 1,
) -> dict[str, Any]:
    return {
        "event_type": "deployment_status",
        "repo": repo,
        "state": state,
        "environment": environment,
        "created_at": created_at or _utcnow(),
        "deployment_id": deployment_id,
    }


def _pr_event(
    repo: str = "org/repo",
    created_at: datetime | None = None,
    pr_number: int = 1,
    commit_sha: str = "abc123",
) -> dict[str, Any]:
    merged_at = created_at or _utcnow()
    return {
        "event_type": "pull_request",
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": commit_sha,
        "merged_at": merged_at,
        "created_at": created_at or _utcnow(),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_url() -> str:
    return TEST_DATABASE_URL  # type: ignore[return-value]


@pytest.fixture(scope="module")
def migrated_db(db_url: str):
    """Run Alembic migrations once per test module against the test database."""
    from store_pg import apply_migrations

    apply_migrations(db_url)
    yield db_url


@pytest.fixture
def store(migrated_db: str):
    """Provide a fresh PostgreSQLEventStore for each test, with a clean slate.

    After each test, all event rows are deleted to ensure test isolation.
    """
    from store_pg import PostgreSQLEventStore

    s = PostgreSQLEventStore(migrated_db)
    yield s
    # Teardown: wipe all events inserted by this test
    s.clear_all_events()


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestPostgreSQLEventStoreProtocolConformance:
    """PostgreSQLEventStore must satisfy the runtime_checkable EventStore Protocol."""

    def test_is_instance_of_event_store_protocol(self, store):
        from store import EventStore

        assert isinstance(store, EventStore)

    def test_store_event_returns_none(self, store):
        result = store.store_event(_push_event())
        assert result is None

    def test_get_events_returns_list(self, store):
        result = store.get_events("org/repo", "push", _utcnow())
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Basic store and retrieve
# ---------------------------------------------------------------------------


class TestPostgreSQLBasicStoreAndRetrieve:
    """Events must survive the round-trip through PostgreSQL."""

    def test_push_event_stored_and_retrieved(self, store):
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        store.store_event(_push_event(created_at=ts))
        results = store.get_events("org/repo", "push", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(results) == 1

    def test_deployment_event_stored_and_retrieved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_deployment_event(created_at=ts))
        results = store.get_events("org/repo", "deployment_status", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(results) == 1

    def test_pr_event_stored_and_retrieved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_pr_event(created_at=ts))
        results = store.get_events("org/repo", "pull_request", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert len(results) == 1

    def test_push_event_fields_preserved_across_round_trip(self, store):
        ts = datetime(2024, 9, 15, 8, 30, 0, tzinfo=timezone.utc)
        store.store_event({
            "event_type": "push",
            "repo": "owner/myservice",
            "ref": "refs/heads/release",
            "commits": [{"sha": "deadbeef", "timestamp": ts}],
            "created_at": ts,
        })
        results = store.get_events("owner/myservice", "push", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert results[0]["ref"] == "refs/heads/release"
        assert results[0]["repo"] == "owner/myservice"

    def test_deployment_event_state_preserved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_deployment_event(state="failure", created_at=ts))
        results = store.get_events("org/repo", "deployment_status", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert results[0]["state"] == "failure"

    def test_deployment_event_environment_preserved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_deployment_event(environment="staging", created_at=ts))
        results = store.get_events("org/repo", "deployment_status", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert results[0]["environment"] == "staging"

    def test_deployment_event_deployment_id_preserved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_deployment_event(deployment_id=42, created_at=ts))
        results = store.get_events("org/repo", "deployment_status", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert results[0]["deployment_id"] == 42

    def test_pr_event_pr_number_preserved(self, store):
        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        store.store_event(_pr_event(pr_number=77, created_at=ts))
        results = store.get_events("org/repo", "pull_request", datetime(2024, 1, 1, tzinfo=timezone.utc))
        assert results[0]["pr_number"] == 77


# ---------------------------------------------------------------------------
# Empty store
# ---------------------------------------------------------------------------


class TestPostgreSQLEmptyStore:
    """A fresh/empty store must return empty lists for all queries."""

    def test_empty_store_returns_empty_list_for_push(self, store):
        assert store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc)) == []

    def test_empty_store_returns_empty_list_for_deployment_status(self, store):
        assert store.get_events("org/repo", "deployment_status", datetime.min.replace(tzinfo=timezone.utc)) == []

    def test_empty_store_returns_empty_list_for_pull_request(self, store):
        assert store.get_events("org/repo", "pull_request", datetime.min.replace(tzinfo=timezone.utc)) == []


# ---------------------------------------------------------------------------
# Filtering: repo
# ---------------------------------------------------------------------------


class TestPostgreSQLFilterByRepo:
    """Repo filter must work correctly."""

    def test_events_for_wrong_repo_not_returned(self, store):
        store.store_event(_push_event(repo="org/target"))
        results = store.get_events("org/other", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert results == []

    def test_events_for_correct_repo_returned(self, store):
        store.store_event(_push_event(repo="org/target"))
        results = store.get_events("org/target", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert len(results) == 1

    def test_multiple_repos_isolated(self, store):
        ts = _utcnow()
        store.store_event(_push_event(repo="org/repo-a", created_at=ts))
        store.store_event(_push_event(repo="org/repo-a", created_at=ts))
        store.store_event(_push_event(repo="org/repo-b", created_at=ts))
        assert len(store.get_events("org/repo-a", "push", datetime.min.replace(tzinfo=timezone.utc))) == 2
        assert len(store.get_events("org/repo-b", "push", datetime.min.replace(tzinfo=timezone.utc))) == 1


# ---------------------------------------------------------------------------
# Filtering: event_type
# ---------------------------------------------------------------------------


class TestPostgreSQLFilterByEventType:
    """Event type filter must work correctly across separate tables."""

    def test_push_events_not_returned_for_deployment_status_query(self, store):
        store.store_event(_push_event())
        results = store.get_events("org/repo", "deployment_status", datetime.min.replace(tzinfo=timezone.utc))
        assert results == []

    def test_deployment_events_not_returned_for_push_query(self, store):
        store.store_event(_deployment_event())
        results = store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert results == []

    def test_three_types_counted_independently(self, store):
        ts = _utcnow()
        for i in range(3):
            store.store_event(_push_event(created_at=ts))
        for i in range(2):
            store.store_event(_deployment_event(created_at=ts, deployment_id=i))
        store.store_event(_pr_event(created_at=ts))
        assert len(store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))) == 3
        assert len(store.get_events("org/repo", "deployment_status", datetime.min.replace(tzinfo=timezone.utc))) == 2
        assert len(store.get_events("org/repo", "pull_request", datetime.min.replace(tzinfo=timezone.utc))) == 1


# ---------------------------------------------------------------------------
# Filtering: since_dt
# ---------------------------------------------------------------------------


class TestPostgreSQLFilterBySinceDt:
    """since_dt filter must return events with created_at >= since_dt."""

    def test_event_at_exact_since_dt_is_included(self, store):
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        store.store_event(_push_event(created_at=ts))
        results = store.get_events("org/repo", "push", ts)
        assert len(results) == 1

    def test_event_before_since_dt_is_excluded(self, store):
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        before = ts - timedelta(seconds=1)
        store.store_event(_push_event(created_at=before))
        results = store.get_events("org/repo", "push", ts)
        assert results == []

    def test_newer_events_included_older_excluded(self, store):
        cutoff = datetime(2024, 6, 1, tzinfo=timezone.utc)
        old_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new_ts = datetime(2024, 12, 1, tzinfo=timezone.utc)
        store.store_event(_push_event(created_at=old_ts))
        store.store_event(_push_event(created_at=new_ts))
        results = store.get_events("org/repo", "push", cutoff)
        assert len(results) == 1
        assert results[0]["created_at"].year == 2024
        assert results[0]["created_at"].month == 12


# ---------------------------------------------------------------------------
# Persistence: data survives across store instances
# ---------------------------------------------------------------------------


class TestPostgreSQLPersistence:
    """Events persisted by one store instance must be visible to a second instance."""

    def test_event_stored_by_one_instance_visible_to_another(self, db_url):
        from store_pg import PostgreSQLEventStore

        ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
        repo = f"persistence-test/repo-{int(ts.timestamp())}"

        store_a = PostgreSQLEventStore(db_url)
        store_a.store_event(_push_event(repo=repo, created_at=ts))

        store_b = PostgreSQLEventStore(db_url)
        results = store_b.get_events(repo, "push", datetime(2024, 1, 1, tzinfo=timezone.utc))

        # Clean up
        store_a.clear_all_events()

        assert len(results) == 1

    def test_two_independent_db_instances_share_same_data(self, db_url):
        from store_pg import PostgreSQLEventStore

        ts = _utcnow()
        repo = f"shared-test/repo-{int(ts.timestamp())}"
        store_1 = PostgreSQLEventStore(db_url)
        store_2 = PostgreSQLEventStore(db_url)

        store_1.store_event(_deployment_event(repo=repo, created_at=ts))
        results = store_2.get_events(repo, "deployment_status", datetime.min.replace(tzinfo=timezone.utc))

        # Clean up
        store_1.clear_all_events()

        assert len(results) == 1


# ---------------------------------------------------------------------------
# Immutability contracts
# ---------------------------------------------------------------------------


class TestPostgreSQLImmutabilityContracts:
    """PostgreSQLEventStore must copy on write and return snapshots."""

    def test_mutating_original_dict_after_store_does_not_affect_stored_copy(self, store):
        original = {
            "event_type": "push",
            "repo": "org/repo",
            "ref": "refs/heads/main",
            "commits": [],
            "created_at": _utcnow(),
            "marker": "original",
        }
        store.store_event(original)
        original["marker"] = "mutated"
        results = store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert results[0]["marker"] == "original"

    def test_get_events_returns_snapshot_clearing_does_not_affect_store(self, store):
        store.store_event(_push_event())
        snapshot = store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))
        snapshot.clear()
        results = store.get_events("org/repo", "push", datetime.min.replace(tzinfo=timezone.utc))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Schema / migration validation
# ---------------------------------------------------------------------------


class TestPostgreSQLSchemaMigration:
    """Alembic migrations must create the expected tables."""

    def test_apply_migrations_is_importable(self):
        from store_pg import apply_migrations

        assert callable(apply_migrations)

    def test_deployment_events_table_exists_after_migration(self, migrated_db):
        """deployment_events table must exist after migrations run."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT tablename FROM pg_tables WHERE tablename = 'deployment_events'"
            ))
            rows = result.fetchall()
        engine.dispose()
        assert len(rows) == 1, "deployment_events table must exist after migration"

    def test_pr_events_table_exists_after_migration(self, migrated_db):
        """pr_events table must exist after migrations run."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT tablename FROM pg_tables WHERE tablename = 'pr_events'"
            ))
            rows = result.fetchall()
        engine.dispose()
        assert len(rows) == 1, "pr_events table must exist after migration"

    def test_push_events_table_exists_after_migration(self, migrated_db):
        """push_events table must exist after migrations run."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT tablename FROM pg_tables WHERE tablename = 'push_events'"
            ))
            rows = result.fetchall()
        engine.dispose()
        assert len(rows) == 1, "push_events table must exist after migration"

    def test_deployment_events_has_required_columns(self, migrated_db):
        """deployment_events must have: id, repo, state, environment, deployment_id, created_at."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'deployment_events'"
            ))
            columns = {row[0] for row in result.fetchall()}
        engine.dispose()
        required = {"id", "repo", "state", "environment", "deployment_id", "created_at"}
        missing = required - columns
        assert not missing, f"Missing columns in deployment_events: {missing}"

    def test_pr_events_has_required_columns(self, migrated_db):
        """pr_events must have: id, repo, pr_number, commit_sha, merged_at, created_at."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'pr_events'"
            ))
            columns = {row[0] for row in result.fetchall()}
        engine.dispose()
        required = {"id", "repo", "pr_number", "commit_sha", "merged_at", "created_at"}
        missing = required - columns
        assert not missing, f"Missing columns in pr_events: {missing}"

    def test_push_events_has_required_columns(self, migrated_db):
        """push_events must have: id, repo, ref, created_at."""
        import sqlalchemy as sa

        engine = sa.create_engine(migrated_db)
        with engine.connect() as conn:
            result = conn.execute(sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'push_events'"
            ))
            columns = {row[0] for row in result.fetchall()}
        engine.dispose()
        required = {"id", "repo", "ref", "created_at"}
        missing = required - columns
        assert not missing, f"Missing columns in push_events: {missing}"

    def test_apply_migrations_is_idempotent(self, migrated_db):
        """Running apply_migrations twice must not raise or produce duplicate tables."""
        from store_pg import apply_migrations

        # Should not raise even when called a second time
        apply_migrations(migrated_db)


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


class TestPostgreSQLEventStoreModuleStructure:
    """store_pg module must be importable and expose required symbols."""

    def test_store_pg_module_is_importable(self):
        import store_pg  # noqa: F401

    def test_postgresql_event_store_class_is_importable(self):
        from store_pg import PostgreSQLEventStore  # noqa: F401

    def test_apply_migrations_function_is_importable(self):
        from store_pg import apply_migrations  # noqa: F401

    def test_postgresql_event_store_accepts_database_url(self, db_url):
        from store_pg import PostgreSQLEventStore

        store = PostgreSQLEventStore(db_url)
        assert store is not None

    def test_clear_all_events_is_callable(self, store):
        """clear_all_events() is a test-support method for resetting state."""
        assert callable(store.clear_all_events)
