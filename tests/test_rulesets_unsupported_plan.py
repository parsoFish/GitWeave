"""Tests: RulesetsManager handles unsupported-plan (403) gracefully.

AC1:
  (a) GithubException(status=403) on GET /orgs/{org}/rulesets →
        list_managed returns []
        apply returns ResourceStatus with status="skipped"
  (b) generic Exception whose str contains "403" →
        exception propagates (is NOT swallowed)
  Also: list_managed docstring names GW_RESOURCE_PREFIX, not FORGE_RESOURCE_PREFIX.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from gitweave.managers.rulesets import RulesetsManager


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_manager(requester_side_effect=None, requester_return=None):
    """Return a RulesetsManager with a faked _requester."""
    org = MagicMock()
    org.login = "test-org"
    if requester_side_effect is not None:
        org._requester.requestJsonAndCheck.side_effect = requester_side_effect
    elif requester_return is not None:
        org._requester.requestJsonAndCheck.return_value = requester_return
    with patch.dict(os.environ, {"GW_RESOURCE_PREFIX": "gw-", "FORGE_RESOURCE_PREFIX": ""}):
        return RulesetsManager(org), org


# ---------------------------------------------------------------------------
# list_managed
# ---------------------------------------------------------------------------

class TestListManagedUnsupportedPlan:
    def test_github_exception_403_returns_empty_list(self):
        """Case (a): GithubException(403) → []."""
        exc = GithubException(403, "Resource not accessible by integration", None)
        mgr, _ = _make_manager(requester_side_effect=exc)
        result = mgr.list_managed()
        assert result == []

    def test_non_github_exception_with_403_message_propagates(self):
        """Case (b): generic Exception with '403' in message → propagates."""
        exc = RuntimeError("403 forbidden from upstream proxy")
        mgr, _ = _make_manager(requester_side_effect=exc)
        with pytest.raises(RuntimeError, match="403"):
            mgr.list_managed()

    def test_other_github_exception_propagates(self):
        """GithubException with non-403 status propagates."""
        exc = GithubException(500, "Internal server error", None)
        mgr, _ = _make_manager(requester_side_effect=exc)
        with pytest.raises(GithubException):
            mgr.list_managed()

    def test_docstring_names_gw_resource_prefix(self):
        """list_managed docstring must mention GW_RESOURCE_PREFIX, not FORGE_RESOURCE_PREFIX."""
        doc = RulesetsManager.list_managed.__doc__ or ""
        assert "GW_RESOURCE_PREFIX" in doc
        assert "FORGE_RESOURCE_PREFIX" not in doc


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

class TestApplyUnsupportedPlan:
    def test_github_exception_403_returns_skipped(self):
        """Case (a): GithubException(403) on list_managed → apply returns skipped."""
        exc = GithubException(403, "Resource not accessible by integration", None)
        mgr, _ = _make_manager(requester_side_effect=exc)
        result = mgr.apply({"name": "gw-test-ruleset"})
        assert result.status == "skipped"

    def test_non_github_exception_with_403_message_propagates(self):
        """Case (b): generic Exception with '403' in message → propagates out of apply."""
        exc = RuntimeError("403 forbidden from upstream proxy")
        mgr, _ = _make_manager(requester_side_effect=exc)
        with pytest.raises(RuntimeError, match="403"):
            mgr.apply({"name": "gw-test-ruleset"})


# ---------------------------------------------------------------------------
# permission-denied 403 (missing token permission, not plan-lacking)
# ---------------------------------------------------------------------------

class TestPermissionDenied:
    """403 responses with an ``errors`` body indicating a missing permission must propagate.

    This is distinct from the org-plan-lacking case (which returns [] / skipped).
    The distinction is made by response body content, not string coercion of the exception.
    """

    def test_403_permission_denied_exits_nonzero(self):
        """GithubException(403) with permission-denied body → propagates from list_managed.

        The exception carries the original API error data including the missing
        permission field name (e.g. ``rule_sets``), so callers can surface it.
        """
        exc = GithubException(
            403,
            {
                "message": "Resource not accessible by integration",
                "errors": [{"code": "missing", "field": "rule_sets"}],
            },
            None,
        )
        mgr, _ = _make_manager(requester_side_effect=exc)
        with pytest.raises(GithubException) as exc_info:
            mgr.list_managed()
        assert exc_info.value.status == 403
        errors = (exc_info.value.data or {}).get("errors", [])
        assert any(e.get("field") == "rule_sets" for e in errors), (
            "Missing permission name 'rule_sets' not found in exception data"
        )
