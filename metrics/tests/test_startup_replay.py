"""TDD tests for startup_replay() — GitHub Events API backfill.

startup_replay() runs once at application startup:
  1. Checks whether the event store is empty for all configured repos.
  2. If empty, fetches the last 24 hours of events from the GitHub Events API
     for each repo listed in GITHUB_REPOS (comma-separated env var).
  3. Parses PushEvent, PullRequestEvent (merged only), and DeploymentStatusEvent
     payloads and stores them using store_event().
  4. If the store is non-empty, the replay is skipped entirely.
  5. Uses GITHUB_TOKEN env var for authentication (Bearer header).
  6. Events older than 24 hours from the time of the call are excluded.
  7. Unknown/unsupported event types are silently skipped.

The function signature is:
  startup_replay(
      store: EventStore,
      github_token: str,
      repos: list[str],
      *,
      http_get: Callable[[str, dict], Response] = _default_http_get,
  ) -> int

Returns the total number of events stored.

These tests mock the HTTP layer. The function must NOT call real GitHub APIs.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_store():
    from store import InMemoryEventStore

    return InMemoryEventStore()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _push_api_event(
    repo: str = "org/repo",
    created_at: datetime | None = None,
    sha: str = "abc123",
    ref: str = "refs/heads/main",
) -> dict[str, Any]:
    """Build a GitHub Events API PushEvent payload."""
    ts = created_at or _utcnow()
    return {
        "type": "PushEvent",
        "repo": {"name": repo},
        "created_at": _iso(ts),
        "payload": {
            "ref": ref,
            "commits": [{"sha": sha, "timestamp": _iso(ts)}],
        },
    }


def _pr_api_event(
    repo: str = "org/repo",
    created_at: datetime | None = None,
    pr_number: int = 42,
    merged: bool = True,
    merged_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a GitHub Events API PullRequestEvent (closed+merged) payload."""
    ts = created_at or _utcnow()
    merge_ts = merged_at or ts
    return {
        "type": "PullRequestEvent",
        "repo": {"name": repo},
        "created_at": _iso(ts),
        "payload": {
            "action": "closed",
            "pull_request": {
                "number": pr_number,
                "merged": merged,
                "merged_at": _iso(merge_ts) if merged else None,
                "merge_commit_sha": "def456" if merged else None,
            },
        },
    }


def _deployment_status_api_event(
    repo: str = "org/repo",
    created_at: datetime | None = None,
    state: str = "success",
    environment: str = "production",
    deployment_id: int = 1,
) -> dict[str, Any]:
    """Build a GitHub Events API DeploymentStatusEvent payload."""
    ts = created_at or _utcnow()
    return {
        "type": "DeploymentStatusEvent",
        "repo": {"name": repo},
        "created_at": _iso(ts),
        "payload": {
            "deployment_status": {
                "state": state,
                "id": deployment_id,
                "created_at": _iso(ts),
                "environment": environment,
            },
            "deployment": {"id": deployment_id},
        },
    }


def _make_response(events: list[dict], status_code: int = 200) -> MagicMock:
    """Create a mock HTTP response with the given events as JSON."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = events
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        from requests.exceptions import HTTPError
        response.raise_for_status.side_effect = HTTPError(f"HTTP {status_code}")
    return response


# ---------------------------------------------------------------------------
# Basic behaviour: skip when store is non-empty
# ---------------------------------------------------------------------------


class TestStartupReplaySkipsWhenStoreNonEmpty:
    """startup_replay must not call the API if the store already has events."""

    def test_replay_skipped_when_store_has_events_for_any_repo(self):
        from startup import startup_replay

        store = _make_store()
        store.store_event({
            "event_type": "push",
            "repo": "org/repo",
            "created_at": _utcnow(),
        })
        http_get = MagicMock()

        count = startup_replay(store, "ghp_token", ["org/repo"], http_get=http_get)

        http_get.assert_not_called()
        assert count == 0

    def test_replay_skipped_returns_zero_events(self):
        from startup import startup_replay

        store = _make_store()
        store.store_event({
            "event_type": "deployment_status",
            "repo": "org/service",
            "created_at": _utcnow(),
        })
        http_get = MagicMock()

        count = startup_replay(store, "token", ["org/service"], http_get=http_get)

        assert count == 0

    def test_replay_skipped_when_any_repo_has_events(self):
        """If any configured repo has events, the whole replay is skipped."""
        from startup import startup_replay

        store = _make_store()
        # Only one of the two repos has events
        store.store_event({
            "event_type": "push",
            "repo": "org/repo-a",
            "created_at": _utcnow(),
        })
        http_get = MagicMock()

        count = startup_replay(store, "token", ["org/repo-a", "org/repo-b"], http_get=http_get)

        http_get.assert_not_called()
        assert count == 0


# ---------------------------------------------------------------------------
# Basic behaviour: fetch when store is empty
# ---------------------------------------------------------------------------


class TestStartupReplayFetchesWhenEmpty:
    """startup_replay must call the GitHub Events API when the store is empty."""

    def test_api_called_for_each_repo_when_store_empty(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([]))

        startup_replay(store, "ghp_abc123", ["org/repo-a", "org/repo-b"], http_get=http_get)

        assert http_get.call_count >= 2
        called_urls = [str(c.args[0]) for c in http_get.call_args_list]
        assert any("org/repo-a" in url for url in called_urls)
        assert any("org/repo-b" in url for url in called_urls)

    def test_api_uses_github_events_endpoint(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([]))

        startup_replay(store, "ghp_token", ["owner/repo"], http_get=http_get)

        called_url = http_get.call_args_list[0].args[0]
        assert "api.github.com" in called_url or "repos/owner/repo/events" in called_url

    def test_api_called_with_authorization_header(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([]))

        startup_replay(store, "ghp_secret_token", ["org/repo"], http_get=http_get)

        _, kwargs = http_get.call_args
        headers = kwargs.get("headers", {})
        assert "Authorization" in headers
        assert "ghp_secret_token" in headers["Authorization"]

    def test_returns_count_of_stored_events(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [
            _push_api_event(created_at=now - timedelta(hours=1)),
            _push_api_event(created_at=now - timedelta(hours=2), sha="xyz789"),
        ]
        http_get = MagicMock(return_value=_make_response(events))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 2


# ---------------------------------------------------------------------------
# Event parsing: PushEvent
# ---------------------------------------------------------------------------


class TestStartupReplayParsesPushEvents:
    """startup_replay must correctly parse and store PushEvent payloads."""

    def test_push_event_is_stored_in_store(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(repo="org/repo", created_at=now - timedelta(hours=1))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert len(results) == 1

    def test_push_event_stored_with_correct_event_type(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(repo="org/repo", created_at=now - timedelta(hours=1))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert results[0]["event_type"] == "push"

    def test_push_event_stored_with_correct_repo(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(repo="owner/service", created_at=now - timedelta(hours=2))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["owner/service"], http_get=http_get)

        results = store.get_events("owner/service", "push", now - timedelta(hours=25))
        assert results[0]["repo"] == "owner/service"

    def test_push_event_stored_with_ref(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(repo="org/repo", created_at=now - timedelta(hours=1), ref="refs/heads/feature")]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert results[0]["ref"] == "refs/heads/feature"

    def test_push_event_stored_with_commits_list(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(repo="org/repo", created_at=now - timedelta(hours=1), sha="commit_sha_123")]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        commits = results[0].get("commits", [])
        assert len(commits) >= 1
        shas = [c.get("sha") for c in commits]
        assert "commit_sha_123" in shas


# ---------------------------------------------------------------------------
# Event parsing: PullRequestEvent (merged only)
# ---------------------------------------------------------------------------


class TestStartupReplayParsesPullRequestEvents:
    """startup_replay must store merged PRs from PullRequestEvent and ignore others."""

    def test_merged_pr_event_is_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_pr_api_event(repo="org/repo", created_at=now - timedelta(hours=3), merged=True)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "pull_request", now - timedelta(hours=25))
        assert len(results) == 1

    def test_merged_pr_event_has_correct_event_type(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_pr_api_event(repo="org/repo", created_at=now - timedelta(hours=1), merged=True)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "pull_request", now - timedelta(hours=25))
        assert results[0]["event_type"] == "pull_request"

    def test_unmerged_closed_pr_event_is_not_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_pr_api_event(repo="org/repo", created_at=now - timedelta(hours=1), merged=False)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "pull_request", now - timedelta(hours=25))
        assert len(results) == 0

    def test_merged_pr_event_has_pr_number(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_pr_api_event(repo="org/repo", created_at=now - timedelta(hours=1), pr_number=99, merged=True)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "pull_request", now - timedelta(hours=25))
        assert results[0]["pr_number"] == 99

    def test_merged_pr_event_has_merged_at_as_datetime(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        merge_time = now - timedelta(hours=2)
        events = [_pr_api_event(repo="org/repo", created_at=now - timedelta(hours=2), merged=True, merged_at=merge_time)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "pull_request", now - timedelta(hours=25))
        assert isinstance(results[0]["merged_at"], datetime)


# ---------------------------------------------------------------------------
# Event parsing: DeploymentStatusEvent
# ---------------------------------------------------------------------------


class TestStartupReplayParsesDeploymentStatusEvents:
    """startup_replay must correctly parse DeploymentStatusEvent payloads."""

    def test_deployment_status_event_is_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_deployment_status_api_event(repo="org/repo", created_at=now - timedelta(hours=1))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "deployment_status", now - timedelta(hours=25))
        assert len(results) == 1

    def test_deployment_status_event_has_state(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_deployment_status_api_event(repo="org/repo", created_at=now - timedelta(hours=1), state="failure")]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "deployment_status", now - timedelta(hours=25))
        assert results[0]["state"] == "failure"

    def test_deployment_status_event_has_environment(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_deployment_status_api_event(
            repo="org/repo",
            created_at=now - timedelta(hours=1),
            environment="staging",
        )]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "deployment_status", now - timedelta(hours=25))
        assert results[0]["environment"] == "staging"

    def test_deployment_status_event_has_deployment_id(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_deployment_status_api_event(repo="org/repo", created_at=now - timedelta(hours=1), deployment_id=77)]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "deployment_status", now - timedelta(hours=25))
        assert results[0]["deployment_id"] == 77


# ---------------------------------------------------------------------------
# 24-hour time window filtering
# ---------------------------------------------------------------------------


class TestStartupReplay24HourWindow:
    """Events older than 24 hours must be excluded; events within 24h must be included."""

    def test_event_within_24h_is_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(created_at=now - timedelta(hours=23, minutes=59))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert len(results) == 1

    def test_event_older_than_24h_is_not_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(created_at=now - timedelta(hours=25))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=26))
        assert len(results) == 0

    def test_event_at_exactly_24h_boundary_is_included(self):
        """Events created exactly 24 hours ago fall within the window."""
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [_push_api_event(created_at=now - timedelta(hours=24))]
        http_get = MagicMock(return_value=_make_response(events))

        startup_replay(store, "token", ["org/repo"], http_get=http_get)

        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert len(results) == 1

    def test_mix_of_old_and_recent_events_only_recent_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [
            _push_api_event(created_at=now - timedelta(hours=1), sha="recent1"),
            _push_api_event(created_at=now - timedelta(hours=12), sha="recent2"),
            _push_api_event(created_at=now - timedelta(hours=25), sha="old1"),
            _push_api_event(created_at=now - timedelta(hours=48), sha="old2"),
        ]
        http_get = MagicMock(return_value=_make_response(events))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 2
        results = store.get_events("org/repo", "push", now - timedelta(hours=25))
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Unknown event types are skipped silently
# ---------------------------------------------------------------------------


class TestStartupReplaySkipsUnknownEventTypes:
    """Events with types other than Push/PullRequest/DeploymentStatus are ignored."""

    def test_watch_event_type_is_skipped(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [
            {
                "type": "WatchEvent",
                "repo": {"name": "org/repo"},
                "created_at": _iso(now - timedelta(hours=1)),
                "payload": {"action": "started"},
            }
        ]
        http_get = MagicMock(return_value=_make_response(events))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_fork_event_is_skipped(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [
            {
                "type": "ForkEvent",
                "repo": {"name": "org/repo"},
                "created_at": _iso(now - timedelta(hours=1)),
                "payload": {},
            }
        ]
        http_get = MagicMock(return_value=_make_response(events))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_unknown_events_interspersed_with_valid_ones_only_valid_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()
        events = [
            _push_api_event(created_at=now - timedelta(hours=1)),
            {
                "type": "IssuesEvent",
                "repo": {"name": "org/repo"},
                "created_at": _iso(now - timedelta(hours=2)),
                "payload": {"action": "opened"},
            },
            _deployment_status_api_event(created_at=now - timedelta(hours=3)),
        ]
        http_get = MagicMock(return_value=_make_response(events))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 2


# ---------------------------------------------------------------------------
# Multiple repos
# ---------------------------------------------------------------------------


class TestStartupReplayMultipleRepos:
    """startup_replay must process each repo independently."""

    def test_events_from_multiple_repos_all_stored(self):
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()

        def http_get_side_effect(url, **kwargs):
            if "org/repo-a" in url:
                return _make_response([_push_api_event(repo="org/repo-a", created_at=now - timedelta(hours=1))])
            if "org/repo-b" in url:
                return _make_response([_push_api_event(repo="org/repo-b", created_at=now - timedelta(hours=2))])
            return _make_response([])

        http_get = MagicMock(side_effect=http_get_side_effect)

        count = startup_replay(store, "token", ["org/repo-a", "org/repo-b"], http_get=http_get)

        assert count == 2
        assert len(store.get_events("org/repo-a", "push", now - timedelta(hours=25))) == 1
        assert len(store.get_events("org/repo-b", "push", now - timedelta(hours=25))) == 1

    def test_empty_repos_list_makes_no_api_calls(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock()

        count = startup_replay(store, "token", [], http_get=http_get)

        http_get.assert_not_called()
        assert count == 0


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------


class TestStartupReplayApiErrorHandling:
    """startup_replay must handle API errors without crashing the application."""

    def test_401_unauthorized_does_not_raise(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([], status_code=401))

        # Should not raise; logs error and returns 0
        count = startup_replay(store, "bad_token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_403_forbidden_does_not_raise(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([], status_code=403))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_404_not_found_does_not_raise(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([], status_code=404))

        count = startup_replay(store, "token", ["org/nonexistent-repo"], http_get=http_get)

        assert count == 0

    def test_500_server_error_does_not_raise(self):
        from startup import startup_replay

        store = _make_store()
        http_get = MagicMock(return_value=_make_response([], status_code=500))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_network_error_does_not_raise(self):
        from startup import startup_replay

        store = _make_store()
        import requests
        http_get = MagicMock(side_effect=requests.exceptions.ConnectionError("Network unreachable"))

        count = startup_replay(store, "token", ["org/repo"], http_get=http_get)

        assert count == 0

    def test_one_repo_error_does_not_prevent_other_repos_from_being_fetched(self):
        """A 404 for one repo must not prevent the other repos from being replayed."""
        from startup import startup_replay

        store = _make_store()
        now = _utcnow()

        def http_get_side_effect(url, **kwargs):
            if "org/repo-a" in url:
                return _make_response([], status_code=404)
            if "org/repo-b" in url:
                return _make_response([_push_api_event(repo="org/repo-b", created_at=now - timedelta(hours=1))])
            return _make_response([])

        http_get = MagicMock(side_effect=http_get_side_effect)

        count = startup_replay(store, "token", ["org/repo-a", "org/repo-b"], http_get=http_get)

        assert count == 1
        assert len(store.get_events("org/repo-b", "push", now - timedelta(hours=25))) == 1


# ---------------------------------------------------------------------------
# Module structure
# ---------------------------------------------------------------------------


class TestStartupReplayModuleStructure:
    """startup_replay must be importable from metrics/src/startup.py."""

    def test_startup_module_is_importable(self):
        import startup  # noqa: F401

    def test_startup_replay_function_is_importable(self):
        from startup import startup_replay  # noqa: F401

    def test_startup_replay_is_callable(self):
        from startup import startup_replay

        assert callable(startup_replay)

    def test_startup_replay_accepts_store_token_repos(self):
        """startup_replay must accept (store, github_token, repos) positional args."""
        import inspect
        from startup import startup_replay

        sig = inspect.signature(startup_replay)
        param_names = list(sig.parameters.keys())
        assert "store" in param_names
        assert "github_token" in param_names
        assert "repos" in param_names
