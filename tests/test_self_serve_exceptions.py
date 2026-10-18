"""Unit tests for gitweave.self_serve.exceptions."""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from gitweave.policy import PolicyDenied
from gitweave.self_serve.exceptions import (
    EXCEPTION_PROPERTY_NAME,
    self_serve_add_exception,
    self_serve_list_exceptions,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

POLICY = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": ["new-repo", "policy-exception"],
            "allowed_repo_patterns": ["platform-*"],
            "allowed_exceptions": ["skip-codeowners", "skip-branch-protection"],
        },
        {
            "slug": "data",
            "allowed_request_types": ["new-repo"],
        },
    ]
}


def _mock_org(org_login: str = "my-org"):
    org = MagicMock()
    org.login = org_login
    # requestJsonAndCheck returns (headers, data) tuple
    org._requester.requestJsonAndCheck = MagicMock(return_value=({}, {}))
    return org


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestPolicyExceptions:
    """Tests for self_serve_add_exception and self_serve_list_exceptions."""

    # AC1: happy-path — allowed team, allowed exception type
    def test_exception_recorded_as_custom_property(self):
        org = _mock_org()
        result = self_serve_add_exception(
            team="platform",
            repo_name="platform-api",
            exception_name="skip-codeowners",
            reason="Legacy repo migration",
            gh_org=org,
            policy=POLICY,
            caller_login="alice",
        )
        assert result == {"applied": True, "property": EXCEPTION_PROPERTY_NAME}
        # Verify org-level schema PATCH was called
        calls = org._requester.requestJsonAndCheck.call_args_list
        schema_calls = [c for c in calls if "properties/schema" in str(c)]
        assert len(schema_calls) >= 1
        # Verify repo-level values PATCH was called
        repo_calls = [c for c in calls if "properties/values" in str(c) and "platform-api" in str(c)]
        assert len(repo_calls) >= 1

    # AC2: idempotent — property definition already exists (422-like error)
    def test_idempotent_when_property_definition_already_exists(self):
        org = _mock_org()

        def _side_effect(method, url, **kwargs):
            if "properties/schema" in url:
                exc = Exception("422 Unprocessable Entity: property already exists")
                exc.status = 422  # use status code, not message substring
                raise exc
            return ({}, {})

        org._requester.requestJsonAndCheck.side_effect = _side_effect

        result = self_serve_add_exception(
            team="platform",
            repo_name="platform-api",
            exception_name="skip-codeowners",
            reason="Re-applying",
            gh_org=org,
            policy=POLICY,
            caller_login="alice",
        )
        assert result == {"applied": True, "property": EXCEPTION_PROPERTY_NAME}

    # AC3: list exceptions reads back custom properties
    def test_list_exceptions_returns_exception_entries(self):
        org = _mock_org()
        org._requester.requestJsonAndCheck.return_value = (
            {},
            [
                {"property_name": "gw-policy-exception", "value": "skip-codeowners"},
                {"property_name": "other-prop", "value": "foo"},
            ],
        )
        result = self_serve_list_exceptions("platform", "platform-api", POLICY, org)
        assert len(result) == 1
        assert result[0]["exception_name"] == "skip-codeowners"

    # AC4: team not in policy → PolicyDenied
    def test_unknown_team_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_exception(
                team="ghost-team",
                repo_name="platform-api",
                exception_name="skip-codeowners",
                reason="test",
                gh_org=org,
                policy=POLICY,
                caller_login="bob",
            )
        org._requester.requestJsonAndCheck.assert_not_called()
        assert "ghost-team" in str(exc_info.value)

    # AC4: team exists but no policy-exception in allowed_request_types
    def test_team_without_exception_permission_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_exception(
                team="data",
                repo_name="data-lake",
                exception_name="skip-codeowners",
                reason="test",
                gh_org=org,
                policy=POLICY,
                caller_login="carol",
            )
        org._requester.requestJsonAndCheck.assert_not_called()
        assert "data" in str(exc_info.value)
        assert "policy-exception" in str(exc_info.value)

    # AC4: exception type not in allowed_exceptions
    def test_disallowed_exception_type_raises_policy_denied(self):
        org = _mock_org()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_exception(
                team="platform",
                repo_name="platform-api",
                exception_name="skip-everything",
                reason="test",
                gh_org=org,
                policy=POLICY,
                caller_login="alice",
            )
        org._requester.requestJsonAndCheck.assert_not_called()
        assert "skip-everything" in str(exc_info.value)
        assert "allowed_exceptions" in str(exc_info.value)
