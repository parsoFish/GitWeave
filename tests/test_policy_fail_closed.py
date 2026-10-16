"""AC8: check_permission and allowed_exceptions guard deny (fail-closed)
when allowed_repo_patterns or allowed_exceptions is absent or empty.
"""
from __future__ import annotations

import pytest
from gitweave.policy import PolicyDenied, check_permission


# ---------------------------------------------------------------------------
# Policies with empty / absent lists
# ---------------------------------------------------------------------------

_POLICY_NO_PATTERNS = {
    "teams": [
        {
            "slug": "eng",
            "allowed_request_types": ["new-repo"],
            # no allowed_repo_patterns key
        }
    ]
}

_POLICY_EMPTY_PATTERNS = {
    "teams": [
        {
            "slug": "eng",
            "allowed_request_types": ["new-repo"],
            "allowed_repo_patterns": [],
        }
    ]
}

_POLICY_NO_EXCEPTIONS = {
    "teams": [
        {
            "slug": "eng",
            "allowed_request_types": ["policy-exception"],
            "allowed_repo_patterns": ["eng-*"],
            # no allowed_exceptions key
        }
    ]
}

_POLICY_EMPTY_EXCEPTIONS = {
    "teams": [
        {
            "slug": "eng",
            "allowed_request_types": ["policy-exception"],
            "allowed_repo_patterns": ["eng-*"],
            "allowed_exceptions": [],
        }
    ]
}


class TestFailClosedRepoPatterns:
    """check_permission denies when allowed_repo_patterns is absent or empty."""

    def test_absent_patterns_denies_repo_request(self):
        with pytest.raises(PolicyDenied, match="fail-closed|empty or absent"):
            check_permission(_POLICY_NO_PATTERNS, "eng", "new-repo", repo_name="eng-svc")

    def test_empty_patterns_denies_repo_request(self):
        with pytest.raises(PolicyDenied, match="fail-closed|empty or absent"):
            check_permission(_POLICY_EMPTY_PATTERNS, "eng", "new-repo", repo_name="eng-svc")

    def test_absent_patterns_names_the_empty_list(self):
        """Error message names the empty list."""
        with pytest.raises(PolicyDenied) as exc_info:
            check_permission(_POLICY_NO_PATTERNS, "eng", "new-repo", repo_name="eng-svc")
        msg = str(exc_info.value)
        assert "allowed_repo_patterns" in msg, f"rule not named in: {msg}"

    def test_empty_patterns_names_the_empty_list(self):
        with pytest.raises(PolicyDenied) as exc_info:
            check_permission(_POLICY_EMPTY_PATTERNS, "eng", "new-repo", repo_name="eng-svc")
        msg = str(exc_info.value)
        assert "allowed_repo_patterns" in msg

    def test_no_repo_name_arg_bypasses_pattern_check(self):
        """If no repo_name passed the pattern check is skipped (still allowed)."""
        result = check_permission(_POLICY_EMPTY_PATTERNS, "eng", "new-repo")
        assert result is True

    def test_non_empty_patterns_still_work(self):
        """A non-empty pattern list still allows matching names."""
        policy = {
            "teams": [{"slug": "eng", "allowed_request_types": ["new-repo"],
                       "allowed_repo_patterns": ["eng-*"]}]
        }
        assert check_permission(policy, "eng", "new-repo", repo_name="eng-api") is True


class TestFailClosedAllowedExceptions:
    """allowed_exceptions guard denies when absent or empty."""

    def test_absent_exceptions_denies(self):
        from gitweave.self_serve.exceptions import self_serve_add_exception
        from unittest.mock import MagicMock

        gh_org = MagicMock()
        with pytest.raises(PolicyDenied, match="fail-closed|empty or absent"):
            self_serve_add_exception(
                "eng", "eng-repo", "skip-codeowners", "urgent",
                gh_org, _POLICY_NO_EXCEPTIONS, "alice"
            )

    def test_empty_exceptions_denies(self):
        from gitweave.self_serve.exceptions import self_serve_add_exception
        from unittest.mock import MagicMock

        gh_org = MagicMock()
        with pytest.raises(PolicyDenied, match="fail-closed|empty or absent"):
            self_serve_add_exception(
                "eng", "eng-repo", "skip-codeowners", "urgent",
                gh_org, _POLICY_EMPTY_EXCEPTIONS, "alice"
            )

    def test_absent_exceptions_names_list(self):
        from gitweave.self_serve.exceptions import self_serve_add_exception
        from unittest.mock import MagicMock

        gh_org = MagicMock()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_exception(
                "eng", "eng-repo", "skip-codeowners", "urgent",
                gh_org, _POLICY_NO_EXCEPTIONS, "alice"
            )
        assert "allowed_exceptions" in str(exc_info.value)

    def test_empty_exceptions_names_list(self):
        from gitweave.self_serve.exceptions import self_serve_add_exception
        from unittest.mock import MagicMock

        gh_org = MagicMock()
        with pytest.raises(PolicyDenied) as exc_info:
            self_serve_add_exception(
                "eng", "eng-repo", "skip-codeowners", "urgent",
                gh_org, _POLICY_EMPTY_EXCEPTIONS, "alice"
            )
        assert "allowed_exceptions" in str(exc_info.value)

    def test_nothing_written_to_org_when_denied(self):
        """Org API never called when exceptions guard denies."""
        from gitweave.self_serve.exceptions import self_serve_add_exception
        from unittest.mock import MagicMock

        gh_org = MagicMock()
        with pytest.raises(PolicyDenied):
            self_serve_add_exception(
                "eng", "eng-repo", "skip-codeowners", "urgent",
                gh_org, _POLICY_EMPTY_EXCEPTIONS, "alice"
            )
        gh_org._requester.requestJsonAndCheck.assert_not_called()
