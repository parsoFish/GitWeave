"""B1 + B2: repo-scope enforcement in self_serve update-content, add-exception, list-exceptions.

B1: update-content and add-exception call check_permission with repo_name; denied when
    allowed_repo_patterns does not match; allowed when it does.
B2: list-exceptions calls check_permission(policy, team, 'policy-exception', repo_name=<repo>)
    before any API read; CLI list-exceptions subcommand takes --team.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from gitweave.policy import PolicyDenied
from gitweave.self_serve.exceptions import self_serve_add_exception, self_serve_list_exceptions
from gitweave.self_serve.update_content import self_serve_update_content

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ALLOWED_REPO = "allowed-repo"
_DENIED_REPO = "other-team-repo"

_POLICY = {
    "teams": [
        {
            "slug": "myteam",
            "allowed_request_types": ["content-update", "policy-exception"],
            "allowed_repo_patterns": ["allowed-*"],
            "allowed_exceptions": ["skip-codeowners"],
            "allowed_content_settings": ["description"],
        }
    ]
}


def _mock_org():
    org = MagicMock()
    org.login = "my-org"
    org._requester.requestJsonAndCheck = MagicMock(return_value=({}, []))
    repo = MagicMock()
    org.get_repo.return_value = repo
    return org


# ---------------------------------------------------------------------------
# B1 — update-content repo scope
# ---------------------------------------------------------------------------


class TestUpdateContentRepoScope:
    """check_permission receives repo_name for update-content."""

    def test_content_update_denied_when_repo_not_in_patterns(self):
        """Denied when repo doesn't match allowed_repo_patterns."""
        with patch("gitweave.self_serve.update_content.check_permission") as spy:
            spy.side_effect = PolicyDenied(
                f"repo_name '{_DENIED_REPO}' does not match any pattern in "
                f"myteam.allowed_repo_patterns: ['allowed-*']"
            )
            with pytest.raises(PolicyDenied) as exc_info:
                self_serve_update_content(
                    team="myteam",
                    repo_name=_DENIED_REPO,
                    setting="description",
                    value="test",
                    gh_org=_mock_org(),
                    policy=_POLICY,
                    caller_login="alice",
                )
        spy.assert_called_once_with(_POLICY, "myteam", "content-update", repo_name=_DENIED_REPO)
        assert "allowed_repo_patterns" in str(exc_info.value)

    def test_content_update_allowed_when_repo_matches_pattern(self):
        """Allowed when repo matches allowed_repo_patterns."""
        org = _mock_org()
        with patch("gitweave.self_serve.update_content.check_permission") as spy:
            spy.return_value = True
            result = self_serve_update_content(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                setting="description",
                value="hello",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )
        spy.assert_called_once_with(_POLICY, "myteam", "content-update", repo_name=_ALLOWED_REPO)
        assert result == {"applied": True}

    def test_content_update_passes_repo_name_to_check_permission(self):
        """check_permission receives repo_name keyword argument."""
        calls_seen = []

        def capturing_check(*args, **kwargs):
            calls_seen.append((args, kwargs))
            return True

        org = _mock_org()
        with patch("gitweave.self_serve.update_content.check_permission", side_effect=capturing_check):
            self_serve_update_content(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                setting="description",
                value="v",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )

        assert calls_seen, "check_permission was never called"
        _, kwargs = calls_seen[0]
        assert kwargs.get("repo_name") == _ALLOWED_REPO, (
            f"check_permission not called with repo_name={_ALLOWED_REPO!r}: {calls_seen}"
        )


# ---------------------------------------------------------------------------
# B1 — add-exception repo scope
# ---------------------------------------------------------------------------


class TestAddExceptionRepoScope:
    """check_permission receives repo_name for add-exception (policy-exception)."""

    def test_policy_exception_denied_when_repo_not_in_patterns(self):
        """Denied when repo doesn't match allowed_repo_patterns."""
        with patch("gitweave.self_serve.exceptions.check_permission") as spy:
            spy.side_effect = PolicyDenied(
                f"repo_name '{_DENIED_REPO}' does not match any pattern in "
                f"myteam.allowed_repo_patterns: ['allowed-*']"
            )
            with pytest.raises(PolicyDenied) as exc_info:
                self_serve_add_exception(
                    team="myteam",
                    repo_name=_DENIED_REPO,
                    exception_name="skip-codeowners",
                    reason="urgent",
                    gh_org=_mock_org(),
                    policy=_POLICY,
                    caller_login="alice",
                )
        spy.assert_called_once_with(_POLICY, "myteam", "policy-exception", repo_name=_DENIED_REPO)
        assert "allowed_repo_patterns" in str(exc_info.value)

    def test_policy_exception_allowed_when_repo_matches_pattern(self):
        """Allowed when repo matches allowed_repo_patterns."""
        org = _mock_org()
        with patch("gitweave.self_serve.exceptions.check_permission") as spy:
            spy.return_value = True
            result = self_serve_add_exception(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                exception_name="skip-codeowners",
                reason="test",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )
        spy.assert_called_once_with(_POLICY, "myteam", "policy-exception", repo_name=_ALLOWED_REPO)
        assert result == {"applied": True, "property": "gw-policy-exception"}

    def test_policy_exception_passes_repo_name_to_check_permission(self):
        """check_permission receives repo_name keyword argument."""
        calls_seen = []

        def capturing_check(*args, **kwargs):
            calls_seen.append((args, kwargs))
            return True

        org = _mock_org()
        with patch("gitweave.self_serve.exceptions.check_permission", side_effect=capturing_check):
            self_serve_add_exception(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                exception_name="skip-codeowners",
                reason="r",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )

        assert calls_seen, "check_permission was never called"
        _, kwargs = calls_seen[0]
        assert kwargs.get("repo_name") == _ALLOWED_REPO, (
            f"check_permission not called with repo_name={_ALLOWED_REPO!r}: {calls_seen}"
        )


# ---------------------------------------------------------------------------
# B2 — list-exceptions repo scope (function-level)
# ---------------------------------------------------------------------------


class TestListExceptionsRepoScope:
    """list-exceptions calls check_permission with repo_name before any API read."""

    def test_list_exceptions_denied_when_repo_not_in_patterns(self):
        """Denied when repo doesn't match allowed_repo_patterns."""
        org = _mock_org()
        with patch("gitweave.self_serve.exceptions.check_permission") as spy:
            spy.side_effect = PolicyDenied(
                f"repo_name '{_DENIED_REPO}' does not match any pattern in "
                f"myteam.allowed_repo_patterns: ['allowed-*']"
            )
            with pytest.raises(PolicyDenied) as exc_info:
                self_serve_list_exceptions(
                    team="myteam",
                    repo_name=_DENIED_REPO,
                    policy=_POLICY,
                    gh_org=org,
                )
        spy.assert_called_once_with(_POLICY, "myteam", "policy-exception", repo_name=_DENIED_REPO)
        assert "allowed_repo_patterns" in str(exc_info.value)
        # API must NOT have been called when denied
        org._requester.requestJsonAndCheck.assert_not_called()

    def test_list_exceptions_allowed_when_repo_matches_pattern(self):
        """Allowed when repo matches; API read proceeds."""
        org = _mock_org()
        org._requester.requestJsonAndCheck.return_value = ({}, [
            {"property_name": "gw-policy-exception", "value": "skip-codeowners"},
        ])
        with patch("gitweave.self_serve.exceptions.check_permission") as spy:
            spy.return_value = True
            result = self_serve_list_exceptions(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                policy=_POLICY,
                gh_org=org,
            )
        spy.assert_called_once_with(_POLICY, "myteam", "policy-exception", repo_name=_ALLOWED_REPO)
        assert len(result) == 1
        assert result[0]["exception_name"] == "skip-codeowners"

    def test_list_exceptions_check_permission_called_before_api_read(self):
        """check_permission fires before requestJsonAndCheck."""
        call_order = []

        def spy_check(*args, **kwargs):
            call_order.append("check_permission")
            return True

        org = _mock_org()
        original_req = org._requester.requestJsonAndCheck

        def spy_req(*args, **kwargs):
            call_order.append("api_read")
            return original_req(*args, **kwargs)

        org._requester.requestJsonAndCheck = spy_req

        with patch("gitweave.self_serve.exceptions.check_permission", side_effect=spy_check):
            self_serve_list_exceptions(
                team="myteam",
                repo_name=_ALLOWED_REPO,
                policy=_POLICY,
                gh_org=org,
            )

        assert call_order[0] == "check_permission", (
            f"check_permission must be called before API read; order was: {call_order}"
        )


# ---------------------------------------------------------------------------
# B2 — CLI list-exceptions takes --team
# ---------------------------------------------------------------------------


class TestListExceptionsCliTeamArg:
    """CLI list-exceptions subcommand accepts and uses --team."""

    def test_cli_list_exceptions_has_team_arg(self):
        """list-exceptions subcommand parser accepts --team."""
        import sys
        from unittest.mock import patch, MagicMock

        mock_list = MagicMock(return_value=[])
        with (
            patch("gitweave.cli._self_serve_auth",
                  return_value=(MagicMock(), _POLICY, "alice")),
            patch("gitweave.cli.self_serve_list_exceptions", mock_list),
            patch("sys.argv", ["gw", "self-serve", "list-exceptions",
                               "--team", "myteam", "--repo", _ALLOWED_REPO]),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()
        assert exc.value.code == 0
        mock_list.assert_called_once_with("myteam", _ALLOWED_REPO, _POLICY, mock_list.call_args[0][3])
