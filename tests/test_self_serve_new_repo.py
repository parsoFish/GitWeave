"""Unit tests for gitweave.self_serve.new_repo."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from github import GithubException

from gitweave.policy import PolicyDenied
from gitweave.self_serve.new_repo import self_serve_new_repo

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

POLICY = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": ["new-repo"],
            "allowed_repo_patterns": ["platform-*", "infra-*"],
        },
        {
            "slug": "data",
            "allowed_request_types": [],
        },
    ]
}


def _mock_org():
    org = MagicMock()
    org.create_repo = MagicMock(return_value=MagicMock())
    return org


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSelfServeNewRepo:
    """Tests for self_serve_new_repo."""

    # AC1: happy-path — allowed team, matching pattern
    def test_creates_repo_when_permitted(self):
        org = _mock_org()
        result = self_serve_new_repo("platform", "platform-svc", org, POLICY, "alice")
        org.create_repo.assert_called_once_with("platform-svc")
        assert result == {"created": True}

    # AC2: idempotent — repo already exists (422)
    def test_idempotent_when_repo_already_exists(self):
        org = _mock_org()
        exc = GithubException(
            status=422,
            data={"message": "Repository creation failed: name already exists on this account"},
            headers={},
        )
        org.create_repo.side_effect = exc
        result = self_serve_new_repo("platform", "platform-svc", org, POLICY, "alice")
        assert result == {"created": False, "reason": "already_exists"}

    # AC3: name violates allowed_repo_patterns
    def test_policy_violation_exits_nonzero(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_new_repo("platform", "rogue-name", org, POLICY, "alice")
        org.create_repo.assert_not_called()
        assert "allowed_repo_patterns" in str(exc_info.value)

    # AC4: team not in policy
    def test_unknown_team_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_new_repo("ghost-team", "any-repo", org, POLICY, "bob")
        org.create_repo.assert_not_called()
        assert "ghost-team" in str(exc_info.value)
        assert "no declared permissions" in str(exc_info.value)
