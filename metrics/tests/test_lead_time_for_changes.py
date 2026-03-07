"""TDD tests for the DORA Lead Time for Changes metric.

Lead Time for Changes: the median time from the earliest commit in a deployment
to when that deployment reached production (successful deployment_status).

Exposed as: gitweave_lead_time_for_changes_hours Prometheus Gauge
Labels: repository, environment
Formula: median(deployment.created_at - earliest_commit.timestamp)
         across all successful deployments in the last 30 days

Commit SHA correlation:
  1. Extract deployment.sha from the deployment_status payload.
  2. Search push events in the store for a commit with that SHA.
  3. Fall back to GET /repos/{owner}/{repo}/commits/{sha} (GitHub API) when
     the SHA is not found in the local event store.
  4. Use the commit's author timestamp as the "code was written" anchor.

Returns 0.0 when no successful deployments exist in the window (not an error).

These tests are written BEFORE implementation (TDD red phase) and will FAIL
until the following modules are created / updated:
  - metrics/src/dora/lead_time_for_changes.py  (new)
  - metrics/src/handlers/deployment_status.py  (updated to store sha + update gauge)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Add src to path so we can import handler modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _dt(
    *,
    days_ago: float = 0,
    hours_ago: float = 0,
    relative_to: datetime | None = None,
) -> datetime:
    """Return a timezone-aware datetime offset from `relative_to` (default: now)."""
    base = relative_to or _utcnow()
    return base - timedelta(days=days_ago, hours=hours_ago)


def _make_store():
    """Return a fresh InMemoryEventStore."""
    from store import InMemoryEventStore

    return InMemoryEventStore()


def _make_deployment_event(
    *,
    repo: str = "octocat/Hello-World",
    environment: str = "production",
    state: str = "success",
    created_at: datetime | None = None,
    deployment_id: int = 1,
    sha: str = "abc123",
) -> dict[str, Any]:
    """Build a normalised deployment_status event dict as stored by the handler.

    The handler is expected to extract deployment.sha from the webhook payload
    and persist it in the event — this test helper creates such an event directly.
    """
    return {
        "event_type": "deployment_status",
        "repo": repo,
        "environment": environment,
        "state": state,
        "created_at": created_at or _utcnow(),
        "deployment_id": deployment_id,
        "sha": sha,  # deployment.sha — the HEAD commit of the deployed ref
    }


def _make_push_event(
    *,
    repo: str = "octocat/Hello-World",
    commits: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a normalised push event dict as stored by the push handler."""
    if commits is None:
        commits = [{"sha": "abc123", "timestamp": _utcnow()}]
    return {
        "event_type": "push",
        "repo": repo,
        "ref": "refs/heads/main",
        "commits": commits,
        "created_at": created_at or _utcnow(),
    }


# ---------------------------------------------------------------------------
# Unit tests — calculate_lead_time_for_changes() pure function
# ---------------------------------------------------------------------------


class TestCalculateLeadTimeForChanges:
    """calculate_lead_time_for_changes(repo, env, store, now, github_client) → float."""

    def test_no_successful_deployments_returns_0_0(self):
        """No deployments in store returns 0.0 — not an error condition."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(0.0)

    def test_single_deployment_with_commit_in_store_returns_correct_hours(self):
        """Deployment 6 hours after the commit yields lead time of exactly 6.0 hours."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        commit_sha = "deadbeef"
        commit_time = _dt(hours_ago=6, relative_to=now)
        deploy_time = now  # deployed right now, commit was 6h ago

        store.store_event(
            _make_push_event(
                commits=[{"sha": commit_sha, "timestamp": commit_time}],
                created_at=commit_time,
            )
        )
        store.store_event(
            _make_deployment_event(
                sha=commit_sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(6.0, abs=1e-3)

    def test_multiple_deployments_median_with_odd_count(self):
        """Median of [2h, 4h, 10h] lead times is 4h (middle value, odd count)."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        # Three deployments with lead times: 2h, 4h, 10h → median = 4h
        lead_times_hours = [2.0, 4.0, 10.0]
        for i, lt in enumerate(lead_times_hours):
            sha = f"sha{i:04d}"
            deploy_time = _dt(days_ago=i + 1, relative_to=now)
            commit_time = _dt(hours_ago=lt, relative_to=deploy_time)

            store.store_event(
                _make_push_event(
                    commits=[{"sha": sha, "timestamp": commit_time}],
                    created_at=commit_time,
                )
            )
            store.store_event(
                _make_deployment_event(
                    sha=sha,
                    created_at=deploy_time,
                    deployment_id=i,
                )
            )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(4.0, abs=1e-3)

    def test_multiple_deployments_median_with_even_count(self):
        """Median of [3h, 5h, 7h, 9h] is the mean of the two middle values: 6.0h."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        # Four deployments with lead times: 3h, 5h, 7h, 9h → median = (5+7)/2 = 6.0h
        lead_times_hours = [3.0, 5.0, 7.0, 9.0]
        for i, lt in enumerate(lead_times_hours):
            sha = f"evsha{i:04d}"
            deploy_time = _dt(days_ago=i + 1, relative_to=now)
            commit_time = _dt(hours_ago=lt, relative_to=deploy_time)

            store.store_event(
                _make_push_event(
                    commits=[{"sha": sha, "timestamp": commit_time}],
                    created_at=commit_time,
                )
            )
            store.store_event(
                _make_deployment_event(
                    sha=sha,
                    created_at=deploy_time,
                    deployment_id=i,
                )
            )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(6.0, abs=1e-3)

    def test_only_success_state_deployments_are_counted(self):
        """failure, pending, in_progress, error deployments are excluded."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "failsha"
        commit_time = _dt(hours_ago=3, relative_to=now)
        deploy_time = now

        store.store_event(
            _make_push_event(
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )

        for i, state in enumerate(["failure", "pending", "in_progress", "error"]):
            store.store_event(
                _make_deployment_event(
                    sha=sha,
                    state=state,
                    created_at=deploy_time,
                    deployment_id=i,
                )
            )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(0.0)

    def test_deployments_older_than_30_days_are_excluded(self):
        """A deployment at 31 days ago falls outside the 30-day window."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "oldsha"
        deploy_time = _dt(days_ago=31, relative_to=now)
        commit_time = _dt(hours_ago=1, relative_to=deploy_time)

        store.store_event(
            _make_push_event(
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )
        store.store_event(
            _make_deployment_event(
                sha=sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(0.0)

    def test_deployment_exactly_30_days_ago_is_included(self):
        """A deployment at exactly 30 days ago (boundary) is included in the window."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "boundarysha"
        deploy_time = now - timedelta(days=30)
        commit_time = _dt(hours_ago=2, relative_to=deploy_time)

        store.store_event(
            _make_push_event(
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )
        store.store_event(
            _make_deployment_event(
                sha=sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(2.0, abs=1e-3)

    def test_filters_by_repository(self):
        """Deployments from a different repository do not affect the target's metric."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "othersha"
        deploy_time = _dt(days_ago=1, relative_to=now)
        commit_time = _dt(hours_ago=5, relative_to=deploy_time)

        # Events for a different repo
        store.store_event(
            _make_push_event(
                repo="other/repo",
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )
        store.store_event(
            _make_deployment_event(
                repo="other/repo",
                sha=sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(0.0)

    def test_filters_by_environment(self):
        """Deployments to staging do not count for the production environment metric."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "stagingsha"
        deploy_time = _dt(days_ago=1, relative_to=now)
        commit_time = _dt(hours_ago=4, relative_to=deploy_time)

        store.store_event(
            _make_push_event(
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )
        store.store_event(
            _make_deployment_event(
                environment="staging",
                sha=sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(0.0)

    def test_uses_earliest_commit_timestamp_when_push_has_multiple_commits(self):
        """When a push contains multiple commits, the earliest timestamp is used.

        If a push includes commits at T-8h and T-3h, and deployment is at T,
        the lead time should be 8h (measured from the earliest commit).
        """
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        deployment_sha = "headsha"
        deploy_time = now

        # Push with 3 commits; deployment sha is the last one but earliest was 8h ago
        commit_early = {"sha": "earliersha", "timestamp": _dt(hours_ago=8, relative_to=now)}
        commit_mid = {"sha": "midsha", "timestamp": _dt(hours_ago=5, relative_to=now)}
        commit_head = {"sha": deployment_sha, "timestamp": _dt(hours_ago=3, relative_to=now)}

        store.store_event(
            _make_push_event(
                commits=[commit_early, commit_mid, commit_head],
            )
        )
        store.store_event(
            _make_deployment_event(
                sha=deployment_sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        # Should be 8h — from the earliest commit in the push that included the deployment SHA
        assert result == pytest.approx(8.0, abs=1e-3)

    def test_deployment_with_no_matching_commit_and_no_github_client_is_skipped(self):
        """When a deployment SHA has no matching push event and no GitHub client, skip it.

        The deployment is excluded from the median calculation rather than crashing.
        If all deployments are excluded, the result is 0.0.
        """
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        # Deployment references a SHA not in any push event
        store.store_event(
            _make_deployment_event(
                sha="unknownsha",
                created_at=_dt(days_ago=1, relative_to=now),
                deployment_id=1,
            )
        )
        # No push event stored at all

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now, github_client=None
        )

        assert result == pytest.approx(0.0)

    @pytest.mark.parametrize(
        "lead_times_hours,expected_median",
        [
            ([1.0], 1.0),
            ([1.0, 3.0], 2.0),           # even: (1+3)/2
            ([1.0, 2.0, 6.0], 2.0),      # odd: middle value
            ([1.0, 2.0, 6.0, 9.0], 4.0), # even: (2+6)/2
            ([0.5, 1.5, 2.5, 3.5, 4.5], 2.5),  # odd: middle value
        ],
    )
    def test_parametrized_median_calculation(self, lead_times_hours, expected_median):
        """Verify median calculation for various sample sizes and distributions."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        for i, lt in enumerate(lead_times_hours):
            sha = f"paramsha{i:04d}"
            deploy_time = _dt(days_ago=i + 1, relative_to=now)
            commit_time = _dt(hours_ago=lt, relative_to=deploy_time)

            store.store_event(
                _make_push_event(
                    commits=[{"sha": sha, "timestamp": commit_time}],
                    created_at=commit_time,
                )
            )
            store.store_event(
                _make_deployment_event(
                    sha=sha,
                    created_at=deploy_time,
                    deployment_id=i,
                )
            )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now
        )

        assert result == pytest.approx(expected_median, abs=1e-3)


# ---------------------------------------------------------------------------
# GitHub API fallback tests
# ---------------------------------------------------------------------------


class TestGitHubApiFallback:
    """When the commit SHA is not in the local event store, fall back to GitHub API."""

    def _make_github_client(self, commit_timestamp: datetime) -> MagicMock:
        """Return a mock GitHub API client that returns the given commit timestamp."""
        client = MagicMock()
        client.get_commit_timestamp.return_value = commit_timestamp
        return client

    def test_github_api_called_when_sha_not_in_store(self):
        """get_commit_timestamp() is called when no push event contains the deployment SHA."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        commit_time = _dt(hours_ago=12, relative_to=now)
        deploy_time = now
        deployment_sha = "notinstore"

        github_client = self._make_github_client(commit_time)

        store.store_event(
            _make_deployment_event(
                sha=deployment_sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )
        # No push event with this SHA in the store

        calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now, github_client=github_client
        )

        github_client.get_commit_timestamp.assert_called_once_with(
            "octocat/Hello-World", deployment_sha
        )

    def test_github_api_fallback_returns_correct_lead_time(self):
        """Lead time is correctly calculated using the timestamp from GitHub API."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        commit_time = _dt(hours_ago=8, relative_to=now)
        deploy_time = now
        deployment_sha = "apionly"

        github_client = self._make_github_client(commit_time)

        store.store_event(
            _make_deployment_event(
                sha=deployment_sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now, github_client=github_client
        )

        assert result == pytest.approx(8.0, abs=1e-3)

    def test_store_lookup_takes_priority_over_github_api(self):
        """When the SHA is found in the event store, the GitHub API is not called."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        sha = "instore"
        commit_time = _dt(hours_ago=3, relative_to=now)
        deploy_time = now

        store.store_event(
            _make_push_event(
                commits=[{"sha": sha, "timestamp": commit_time}],
            )
        )
        store.store_event(
            _make_deployment_event(
                sha=sha,
                created_at=deploy_time,
                deployment_id=1,
            )
        )

        github_client = MagicMock()

        calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now, github_client=github_client
        )

        github_client.get_commit_timestamp.assert_not_called()

    def test_github_api_fallback_uses_github_token_env_var(self):
        """GitHubCommitClient reads GITHUB_TOKEN from the environment."""
        from dora.lead_time_for_changes import GitHubCommitClient

        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token-abc"}):
            client = GitHubCommitClient()

        assert client.token == "test-token-abc"

    def test_github_commit_client_calls_correct_endpoint(self):
        """GitHubCommitClient requests GET /repos/{owner}/{repo}/commits/{sha}."""
        from dora.lead_time_for_changes import GitHubCommitClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "commit": {
                "author": {
                    "date": "2024-01-15T10:00:00Z"
                }
            }
        }

        with patch("requests.get", return_value=mock_response) as mock_get:
            with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
                client = GitHubCommitClient()
                result = client.get_commit_timestamp("octocat/Hello-World", "abc123")

        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "octocat/Hello-World" in call_url
        assert "abc123" in call_url
        assert "commits" in call_url

    def test_github_commit_client_returns_parsed_datetime(self):
        """get_commit_timestamp() returns a timezone-aware datetime from commit.author.date."""
        from dora.lead_time_for_changes import GitHubCommitClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "commit": {
                "author": {
                    "date": "2024-01-15T10:00:00Z"
                }
            }
        }

        with patch("requests.get", return_value=mock_response):
            with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
                client = GitHubCommitClient()
                result = client.get_commit_timestamp("octocat/Hello-World", "abc123")

        assert result is not None
        assert result.tzinfo is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_github_commit_client_returns_none_on_404(self):
        """get_commit_timestamp() returns None when the SHA is not found (404)."""
        from dora.lead_time_for_changes import GitHubCommitClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}):
                client = GitHubCommitClient()
                result = client.get_commit_timestamp("octocat/Hello-World", "missingsha")

        assert result is None

    def test_deployment_excluded_when_github_api_returns_none(self):
        """When GitHub API returns None for a SHA, that deployment is skipped in the median."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        store = _make_store()
        now = _utcnow()

        github_client = MagicMock()
        github_client.get_commit_timestamp.return_value = None

        store.store_event(
            _make_deployment_event(
                sha="ghostsha",
                created_at=_dt(days_ago=1, relative_to=now),
                deployment_id=1,
            )
        )

        result = calculate_lead_time_for_changes(
            "octocat/Hello-World", "production", store, now, github_client=github_client
        )

        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Prometheus gauge registration tests
# ---------------------------------------------------------------------------


class TestLeadTimeGaugeRegistration:
    """gitweave_lead_time_for_changes_hours Prometheus gauge must be registered correctly."""

    def test_lead_time_gauge_is_importable(self):
        """LEAD_TIME_GAUGE constant must be importable from the module."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE

        assert LEAD_TIME_GAUGE is not None

    def test_gauge_name_is_gitweave_lead_time_for_changes_hours(self):
        """The Prometheus metric name must be 'gitweave_lead_time_for_changes_hours'."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE

        assert LEAD_TIME_GAUGE._name == "gitweave_lead_time_for_changes_hours"

    def test_gauge_has_repository_label(self):
        """The gauge must carry a 'repository' label for per-repo cardinality."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE

        assert "repository" in LEAD_TIME_GAUGE._labelnames

    def test_gauge_has_environment_label(self):
        """The gauge must carry an 'environment' label for per-environment cardinality."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE

        assert "environment" in LEAD_TIME_GAUGE._labelnames

    def test_gauge_has_exactly_two_labels(self):
        """The gauge must have exactly two labels: repository and environment."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE

        assert set(LEAD_TIME_GAUGE._labelnames) == {"repository", "environment"}

    def test_calculate_lead_time_for_changes_is_callable(self):
        """calculate_lead_time_for_changes must be a callable exported from the module."""
        from dora.lead_time_for_changes import calculate_lead_time_for_changes

        assert callable(calculate_lead_time_for_changes)

    def test_github_commit_client_is_importable(self):
        """GitHubCommitClient must be importable from the module."""
        from dora.lead_time_for_changes import GitHubCommitClient

        assert GitHubCommitClient is not None


# ---------------------------------------------------------------------------
# deployment_status handler — SHA extraction tests
# ---------------------------------------------------------------------------


class TestDeploymentStatusHandlerStoresSha:
    """The deployment_status handler must extract and store deployment.sha.

    This field is required for the lead time correlation. Without it, we cannot
    look up which push event introduced the deployed code.
    """

    def _make_payload(
        self,
        *,
        state: str = "success",
        sha: str = "a84d88e7554fc1fa21bcebb4664407ac2b3aac",
        environment: str = "production",
        deployment_id: int = 1,
    ) -> dict[str, Any]:
        """Build a minimal deployment_status webhook payload including deployment.sha."""
        return {
            "deployment_status": {
                "state": state,
                "id": deployment_id,
                "created_at": _utcnow().isoformat(),
                "environment": environment,
            },
            "deployment": {
                "sha": sha,
                "id": deployment_id,
            },
            "repository": {"full_name": "octocat/Hello-World"},
        }

    def test_handler_stores_deployment_sha_in_event(self):
        """handle() must extract deployment.sha and persist it in the normalised event."""
        from handlers.deployment_status import handle

        store = _make_store()
        expected_sha = "deadbeef1234567890abcdef"
        payload = self._make_payload(sha=expected_sha)

        event = handle(payload, store)

        assert event.get("sha") == expected_sha, (
            f"Expected event['sha'] == {expected_sha!r}, got {event.get('sha')!r}. "
            "The handler must extract deployment.sha from payload['deployment']['sha'] "
            "and include it in the stored event."
        )

    def test_stored_event_contains_sha(self):
        """The event persisted in the store must include the 'sha' field."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        expected_sha = "cafebabe"
        payload = self._make_payload(sha=expected_sha)

        handle(payload, store)

        # Retrieve the stored event and verify sha is present
        from datetime import timedelta
        stored = store.get_events(
            "octocat/Hello-World",
            "deployment_status",
            since_dt=_utcnow() - timedelta(minutes=1),
        )
        assert len(stored) == 1
        assert stored[0].get("sha") == expected_sha

    def test_handler_raises_400_when_deployment_field_missing(self):
        """handle() raises HTTPException(400) when the 'deployment' key is absent."""
        from handlers.deployment_status import handle
        from fastapi import HTTPException

        store = _make_store()
        payload = {
            "deployment_status": {
                "state": "success",
                "id": 1,
                "created_at": _utcnow().isoformat(),
                "environment": "production",
            },
            # 'deployment' key intentionally omitted
            "repository": {"full_name": "octocat/Hello-World"},
        }

        with pytest.raises(HTTPException) as exc_info:
            handle(payload, store)

        assert exc_info.value.status_code == 400

    def test_handler_raises_400_when_deployment_sha_missing(self):
        """handle() raises HTTPException(400) when deployment.sha is absent."""
        from handlers.deployment_status import handle
        from fastapi import HTTPException

        store = _make_store()
        payload = {
            "deployment_status": {
                "state": "success",
                "id": 1,
                "created_at": _utcnow().isoformat(),
                "environment": "production",
            },
            "deployment": {
                # 'sha' key intentionally omitted
                "id": 1,
            },
            "repository": {"full_name": "octocat/Hello-World"},
        }

        with pytest.raises(HTTPException) as exc_info:
            handle(payload, store)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Integration tests — gauge updates synchronously after handle()
# ---------------------------------------------------------------------------


class TestLeadTimeGaugeUpdatesAfterHandle:
    """The Prometheus gauge must reflect the current lead time after each handle() call."""

    def _read_gauge(self, repo: str, environment: str) -> float:
        """Read the current value of the lead time gauge for a given repo+environment."""
        from dora.lead_time_for_changes import LEAD_TIME_GAUGE
        from prometheus_client import REGISTRY

        for metric in REGISTRY.collect():
            if metric.name == "gitweave_lead_time_for_changes_hours":
                for sample in metric.samples:
                    if (
                        sample.labels.get("repository") == repo
                        and sample.labels.get("environment") == environment
                    ):
                        return sample.value
        return 0.0

    def test_gauge_updated_after_successful_deployment_with_known_commit(self):
        """Gauge reflects the lead time after a success event is handled end-to-end."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = _utcnow()

        # Pre-seed a push event 4 hours ago with a known SHA
        commit_sha = "integrationsha001"
        commit_time = _dt(hours_ago=4, relative_to=now)
        store.store_event(
            _make_push_event(
                repo="integration-test/gauge",
                commits=[{"sha": commit_sha, "timestamp": commit_time}],
            )
        )

        # Handle a success deployment referencing that SHA
        payload = {
            "deployment_status": {
                "state": "success",
                "id": 1001,
                "created_at": now.isoformat(),
                "environment": "production",
            },
            "deployment": {"sha": commit_sha, "id": 1001},
            "repository": {"full_name": "integration-test/gauge"},
        }

        handle(payload, store)

        gauge_value = self._read_gauge("integration-test/gauge", "production")
        assert gauge_value > 0.0, (
            "Gauge must be non-zero after a successful deployment with a known commit"
        )
        assert gauge_value == pytest.approx(4.0, abs=0.1)

    def test_gauge_not_updated_for_failure_deployment(self):
        """A failure deployment_status must not increase the lead time gauge."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()

        payload = {
            "deployment_status": {
                "state": "failure",
                "id": 2002,
                "created_at": _utcnow().isoformat(),
                "environment": "production",
            },
            "deployment": {"sha": "failsha002", "id": 2002},
            "repository": {"full_name": "failure-lt-test/repo"},
        }

        handle(payload, store)

        gauge_value = self._read_gauge("failure-lt-test/repo", "production")
        assert gauge_value == pytest.approx(0.0), (
            "Gauge must remain 0.0 when only failure deployments have been processed"
        )

    def test_gauge_independent_per_repo_and_environment(self):
        """Lead time gauge for repo-A/production is independent of repo-B/staging."""
        from handlers.deployment_status import handle
        from store import InMemoryEventStore

        store = InMemoryEventStore()
        now = _utcnow()

        # 2h lead time for repo-A / production
        sha_a = "ltrepo_a_sha"
        store.store_event(
            _make_push_event(
                repo="lt-isolation/repo-a",
                commits=[{"sha": sha_a, "timestamp": _dt(hours_ago=2, relative_to=now)}],
            )
        )
        handle(
            {
                "deployment_status": {
                    "state": "success",
                    "id": 1,
                    "created_at": now.isoformat(),
                    "environment": "production",
                },
                "deployment": {"sha": sha_a, "id": 1},
                "repository": {"full_name": "lt-isolation/repo-a"},
            },
            store,
        )

        # 10h lead time for repo-B / staging
        sha_b = "ltrepo_b_sha"
        store.store_event(
            _make_push_event(
                repo="lt-isolation/repo-b",
                commits=[{"sha": sha_b, "timestamp": _dt(hours_ago=10, relative_to=now)}],
            )
        )
        handle(
            {
                "deployment_status": {
                    "state": "success",
                    "id": 2,
                    "created_at": now.isoformat(),
                    "environment": "staging",
                },
                "deployment": {"sha": sha_b, "id": 2},
                "repository": {"full_name": "lt-isolation/repo-b"},
            },
            store,
        )

        gauge_a = self._read_gauge("lt-isolation/repo-a", "production")
        gauge_b = self._read_gauge("lt-isolation/repo-b", "staging")

        assert gauge_a == pytest.approx(2.0, abs=0.1)
        assert gauge_b == pytest.approx(10.0, abs=0.1)


# ---------------------------------------------------------------------------
# Module structure tests — ensure dora package exports are discoverable
# ---------------------------------------------------------------------------


class TestLeadTimeModuleStructure:
    """The lead time module must be correctly structured under metrics/src/dora/."""

    def test_dora_lead_time_module_is_importable(self):
        """import dora.lead_time_for_changes must succeed."""
        import dora.lead_time_for_changes  # noqa: F401

    def test_lead_time_gauge_exported_at_module_level(self):
        """LEAD_TIME_GAUGE must be a module-level name in dora.lead_time_for_changes."""
        import dora.lead_time_for_changes as ltm

        assert hasattr(ltm, "LEAD_TIME_GAUGE")

    def test_github_commit_client_exported_at_module_level(self):
        """GitHubCommitClient must be a module-level class in dora.lead_time_for_changes."""
        import dora.lead_time_for_changes as ltm

        assert hasattr(ltm, "GitHubCommitClient")
        assert callable(ltm.GitHubCommitClient)
