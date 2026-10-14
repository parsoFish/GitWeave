"""Unit tests for gitweave.self_serve.update_content."""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from gitweave.policy import PolicyDenied
from gitweave.self_serve.update_content import self_serve_update_content

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

POLICY = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": ["content-update"],
            "allowed_content_settings": [
                "branch_protection",
                "topics",
                "repo_variables",
                "environments",
                "description",
            ],
        },
        {
            "slug": "data",
            "allowed_request_types": ["content-update"],
            "allowed_content_settings": ["topics"],
        },
        {
            "slug": "readonly",
            "allowed_request_types": [],
            "allowed_content_settings": [],
        },
    ]
}


def _mock_org(repo_mock=None):
    org = MagicMock()
    if repo_mock is None:
        repo_mock = MagicMock()
    org.get_repo = MagicMock(return_value=repo_mock)
    return org, repo_mock


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestUpdateContent:
    """Tests for self_serve_update_content."""

    # AC1: happy path — allowed team, allowed setting, returns success
    def test_applies_setting_and_returns_success(self):
        org, repo = _mock_org()
        result = self_serve_update_content(
            "platform", "platform-svc", "topics", ["python", "api"],
            org, POLICY, "alice"
        )
        assert result == {"applied": True}
        repo.replace_topics.assert_called_once_with(["python", "api"])

    # AC2: branch_protection — calls edit_protection with provided params
    def test_branch_protection_calls_edit_protection(self):
        org, repo = _mock_org()
        branch_mock = MagicMock()
        repo.get_branch = MagicMock(return_value=branch_mock)
        value = {"branch": "main", "required_approving_review_count": 2}
        result = self_serve_update_content(
            "platform", "platform-svc", "branch_protection", value,
            org, POLICY, "alice"
        )
        assert result == {"applied": True}
        repo.get_branch.assert_called_once_with("main")
        branch_mock.edit_protection.assert_called_once_with(
            required_approving_review_count=2
        )

    # AC3: topics — calls replace_topics with provided list
    def test_topics_calls_replace_topics(self):
        org, repo = _mock_org()
        result = self_serve_update_content(
            "platform", "platform-svc", "topics", ["ml", "data"],
            org, POLICY, "alice"
        )
        assert result == {"applied": True}
        repo.replace_topics.assert_called_once_with(["ml", "data"])

    # AC4: setting not in team's allowed_content_settings raises PolicyDenied
    def test_disallowed_setting_raises_policy_denied(self):
        org, repo = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_update_content(
                "data", "data-svc", "branch_protection",
                {"branch": "main"}, org, POLICY, "bob"
            )
        org.get_repo.assert_not_called()
        err = str(exc_info.value)
        assert "branch_protection" in err
        assert "data" in err

    # AC5: team not in policy raises PolicyDenied naming the team
    def test_unknown_team_raises_policy_denied(self):
        org, repo = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_update_content(
                "ghost-team", "any-repo", "topics", [],
                org, POLICY, "carol"
            )
        org.get_repo.assert_not_called()
        assert "ghost-team" in str(exc_info.value)

    # Also: team present but content-update not in allowed_request_types
    def test_policy_violation_exits_nonzero(self):
        """Gate test: team has no content-update permission."""
        org, repo = _mock_org()
        with pytest.raises(PolicyDenied):
            self_serve_update_content(
                "readonly", "any-repo", "topics", [],
                org, POLICY, "dave"
            )
        org.get_repo.assert_not_called()
