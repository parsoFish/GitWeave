"""Unit tests for gitweave.self_serve.membership."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from github import GithubException

from gitweave.policy import PolicyDenied
from gitweave.self_serve.membership import self_serve_add_member, self_serve_remove_member

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

POLICY = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": ["team-membership"],
        },
        {
            "slug": "data",
            "allowed_request_types": [],
        },
    ]
}


def _mock_org(caller_state: str = "active"):
    """Return a mock gh_org where the caller's membership state is *caller_state*."""
    org = MagicMock()
    gh_team = MagicMock()

    membership = MagicMock()
    membership.state = caller_state
    gh_team.get_team_membership.return_value = membership
    gh_team.add_membership = MagicMock()
    gh_team.remove_membership = MagicMock()

    org.get_team_by_slug.return_value = gh_team
    return org


def _mock_gh(login: str):
    """Return a mock root Github client whose get_user returns a NamedUser mock."""
    gh = MagicMock()
    user = MagicMock()
    user.login = login
    gh.get_user.return_value = user
    return gh


def _mock_org_no_membership():
    """Return a mock gh_org where membership check raises 404 (caller not in team)."""
    org = MagicMock()
    gh_team = MagicMock()

    exc = GithubException(status=404, data={"message": "Not Found"}, headers={})
    gh_team.get_team_membership.side_effect = exc

    org.get_team_by_slug.return_value = gh_team
    return org


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSelfServeMembership:
    """Tests for self_serve_add_member and self_serve_remove_member."""

    # AC1: happy path — caller is active member, policy allows team-membership
    def test_add_member_when_permitted(self):
        org = _mock_org(caller_state="active")
        gh = _mock_gh("new-hire")
        result = self_serve_add_member("platform", "new-hire", org, POLICY, "alice", gh=gh)
        org.get_team_by_slug.assert_called_once_with("platform")
        gh.get_user.assert_called_once_with("new-hire")
        org.get_team_by_slug.return_value.add_membership.assert_called_once_with(
            gh.get_user.return_value
        )
        assert result == {"applied": True}

    # AC2: caller not in team AND adding someone else → PolicyDenied (sentinel gate test)
    def test_policy_violation_exits_nonzero(self):
        org = _mock_org_no_membership()
        gh = _mock_gh("new-hire")
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_member("platform", "new-hire", org, POLICY, "not-a-member", gh=gh)
        org.get_team_by_slug.return_value.add_membership.assert_not_called()
        assert "not-a-member" in str(exc_info.value)
        assert "member" in str(exc_info.value).lower()

    # AC2 self-join: caller not in team but adding self → allowed (policy gates, no membership pre-check)
    def test_self_join_allowed_when_not_member(self):
        org = _mock_org_no_membership()
        gh = _mock_gh("requester")
        # caller_login == member_login — self-join path, no membership check
        result = self_serve_add_member("platform", "requester", org, POLICY, "requester", gh=gh)
        org.get_team_by_slug.return_value.add_membership.assert_called_once()
        assert result == {"applied": True}

    # AC2 variant: membership exists but state is not active
    def test_pending_caller_is_denied(self):
        org = _mock_org(caller_state="pending")
        gh = _mock_gh("new-hire")
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_member("platform", "new-hire", org, POLICY, "alice", gh=gh)
        org.get_team_by_slug.return_value.add_membership.assert_not_called()
        assert "alice" in str(exc_info.value)

    # AC3: team not in policy → PolicyDenied naming the team
    def test_unknown_team_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_member("ghost-team", "new-hire", org, POLICY, "alice")
        org.get_team_by_slug.assert_not_called()
        assert "ghost-team" in str(exc_info.value)
        assert "no declared permissions" in str(exc_info.value)

    # AC4: happy path remove — caller is active member, policy allows team-membership
    def test_remove_member_when_permitted(self):
        org = _mock_org(caller_state="active")
        gh = _mock_gh("leaver")
        result = self_serve_remove_member("platform", "leaver", org, POLICY, "alice", gh=gh)
        org.get_team_by_slug.assert_called_once_with("platform")
        gh.get_user.assert_called_once_with("leaver")
        org.get_team_by_slug.return_value.remove_membership.assert_called_once_with(
            gh.get_user.return_value
        )
        assert result == {"applied": True}

    # AC4 guard: remove denied when team not in policy
    def test_remove_unknown_team_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_remove_member("ghost-team", "leaver", org, POLICY, "alice")
        org.get_team_by_slug.assert_not_called()
        assert "ghost-team" in str(exc_info.value)

    # Team in policy but permission not granted
    def test_team_without_permission_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_member("data", "new-hire", org, POLICY, "alice")
        org.get_team_by_slug.assert_not_called()
        assert "data" in str(exc_info.value)
