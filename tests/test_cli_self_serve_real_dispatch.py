"""AC14: Real CLI dispatch tests for self-serve commands — add-member, add-exception, update-content.

Each test dispatches through gitweave.cli.main() (real parser + real dispatch),
only HTTP/API calls are faked via MagicMock on the org client.

Asserts the WRITE request each command makes (method, path / call).
A handler that skips its write fails the test.
"""
from __future__ import annotations

import contextlib
import io
import sys
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TEAM = "platform"
_MEMBER = "alice"
_REPO = "allowed-repo"
_EXCEPTION = "skip-codeowners"
_REASON = "test reason"
_SETTING = "description"
_VALUE = "my description"

_POLICY = {
    "teams": [
        {
            "slug": _TEAM,
            "allowed_request_types": ["content-update", "policy-exception", "team-membership"],
            "allowed_repo_patterns": ["allowed-*"],
            "allowed_exceptions": [_EXCEPTION],
            "allowed_content_settings": [_SETTING],
            "allowed_modules": [],
        }
    ]
}


def _make_gh_org():
    org = MagicMock()
    org.login = "my-org"

    # Team mock for add-member
    team = MagicMock()
    team.get_team_membership = MagicMock(
        return_value=MagicMock(state="active")
    )
    team.add_membership = MagicMock()
    org.get_team_by_slug.return_value = team

    # Repo mock
    repo = MagicMock()
    org.get_repo.return_value = repo

    # Requester mock for exceptions/properties
    org._requester.requestJsonAndCheck = MagicMock(return_value=({}, []))

    # gh.get_user()
    org.get_user = MagicMock(return_value=MagicMock())

    return org


def _dispatch(argv: list[str], gh_org) -> tuple[int, str, str]:
    """Dispatch main() in-process; return (exit_code, stdout, stderr)."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0

    def _fake_auth():
        return gh_org, _POLICY, _MEMBER

    fake_gh = MagicMock()
    fake_gh.get_user = MagicMock(return_value=MagicMock())

    with (
        patch("sys.argv", argv),
        patch("gitweave.cli._self_serve_auth", side_effect=_fake_auth),
        patch("gitweave.self_serve.membership.get_github_client", return_value=fake_gh),
        contextlib.redirect_stdout(stdout_buf),
        contextlib.redirect_stderr(stderr_buf),
    ):
        with pytest.raises(SystemExit) as exc_info:
            from gitweave.cli import main
            main()
        exit_code = exc_info.value.code

    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# add-member — real dispatch
# ---------------------------------------------------------------------------


class TestAddMemberRealDispatch:
    """AC14: add-member dispatched through real CLI parser makes the write call."""

    def test_add_member_exits_zero(self):
        gh_org = _make_gh_org()
        exit_code, _, _ = _dispatch(
            ["gw", "self-serve", "add-member", "--team", _TEAM, "--member", _MEMBER],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

    def test_add_member_calls_add_membership(self):
        """The write: gh_team.add_membership(user) must be called."""
        gh_org = _make_gh_org()
        _dispatch(
            ["gw", "self-serve", "add-member", "--team", _TEAM, "--member", _MEMBER],
            gh_org,
        )
        team = gh_org.get_team_by_slug.return_value
        team.add_membership.assert_called_once()

    def test_add_member_noop_fails(self):
        """A handler that skips add_membership causes the assertion to fail."""
        gh_org = _make_gh_org()
        # Override add_membership to be a no-op that never records a call
        # We verify by checking that add_membership was indeed called
        gh_org.get_team_by_slug.return_value.add_membership = MagicMock()
        _dispatch(
            ["gw", "self-serve", "add-member", "--team", _TEAM, "--member", _MEMBER],
            gh_org,
        )
        team = gh_org.get_team_by_slug.return_value
        # If the CLI skipped the write, this assertion fails — that's the point
        assert team.add_membership.call_count >= 1, (
            "add-member CLI must call add_membership; a no-op implementation fails here"
        )


# ---------------------------------------------------------------------------
# add-exception — real dispatch
# ---------------------------------------------------------------------------


class TestAddExceptionRealDispatch:
    """AC14: add-exception dispatched through real CLI parser makes the write call."""

    def test_add_exception_exits_zero(self):
        gh_org = _make_gh_org()
        exit_code, _, _ = _dispatch(
            [
                "gw", "self-serve", "add-exception",
                "--team", _TEAM, "--repo", _REPO,
                "--exception", _EXCEPTION, "--reason", _REASON,
            ],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

    def test_add_exception_calls_property_write(self):
        """The write: PATCH /repos/{org}/{repo}/properties/values must be called."""
        gh_org = _make_gh_org()
        _dispatch(
            [
                "gw", "self-serve", "add-exception",
                "--team", _TEAM, "--repo", _REPO,
                "--exception", _EXCEPTION, "--reason", _REASON,
            ],
            gh_org,
        )
        # requestJsonAndCheck must have been called with PATCH for properties
        patch_calls = [
            c for c in gh_org._requester.requestJsonAndCheck.call_args_list
            if c.args[0] == "PATCH" and "properties" in str(c.args[1])
        ]
        assert patch_calls, (
            "add-exception must PATCH /repos/.../properties/values; "
            f"calls seen: {gh_org._requester.requestJsonAndCheck.call_args_list}"
        )

    def test_add_exception_property_write_includes_value(self):
        """The PATCH body must include the exception name as the property value."""
        gh_org = _make_gh_org()
        _dispatch(
            [
                "gw", "self-serve", "add-exception",
                "--team", _TEAM, "--repo", _REPO,
                "--exception", _EXCEPTION, "--reason", _REASON,
            ],
            gh_org,
        )
        patch_calls = [
            c for c in gh_org._requester.requestJsonAndCheck.call_args_list
            if c.args[0] == "PATCH" and "properties/values" in str(c.args[1])
        ]
        assert patch_calls, "No PATCH /properties/values call found"
        _, kwargs = patch_calls[-1].args, patch_calls[-1].kwargs
        body = patch_calls[-1].kwargs.get("input", {})
        props = body.get("properties", [])
        values = [p.get("value") for p in props]
        assert _EXCEPTION in values, (
            f"Expected exception '{_EXCEPTION}' in PATCH body properties.value; got {values}"
        )

    def test_add_exception_noop_fails(self):
        """A handler that skips the PATCH write causes the assertion to fail."""
        gh_org = _make_gh_org()
        # Make requestJsonAndCheck a no-op that records nothing for PATCH
        real_calls = []
        original = gh_org._requester.requestJsonAndCheck

        def _recording(*args, **kwargs):
            real_calls.append((args, kwargs))
            return original(*args, **kwargs)

        gh_org._requester.requestJsonAndCheck = _recording
        _dispatch(
            [
                "gw", "self-serve", "add-exception",
                "--team", _TEAM, "--repo", _REPO,
                "--exception", _EXCEPTION, "--reason", _REASON,
            ],
            gh_org,
        )
        patch_calls = [c for c in real_calls if c[0][0] == "PATCH" and "properties" in str(c[0][1])]
        assert patch_calls, (
            "add-exception CLI must PATCH /repos/.../properties/values; skipping the write fails here"
        )


# ---------------------------------------------------------------------------
# update-content — real dispatch (AC14 also covers update-content)
# ---------------------------------------------------------------------------


class TestUpdateContentRealDispatchAC14:
    """AC14: update-content dispatched through real CLI makes the write call."""

    def test_update_content_exits_zero(self):
        gh_org = _make_gh_org()
        exit_code, _, _ = _dispatch(
            [
                "gw", "self-serve", "update-content",
                "--team", _TEAM, "--repo", _REPO,
                "--setting", _SETTING, "--value", _VALUE,
            ],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}"

    def test_update_content_calls_edit_topics_or_description(self):
        """The write: repo.edit() or repo.replace_topics() must be called."""
        gh_org = _make_gh_org()
        repo = gh_org.get_repo.return_value
        _dispatch(
            [
                "gw", "self-serve", "update-content",
                "--team", _TEAM, "--repo", _REPO,
                "--setting", _SETTING, "--value", _VALUE,
            ],
            gh_org,
        )
        # description uses repo.edit()
        assert repo.edit.call_count >= 1 or repo.replace_topics.call_count >= 1, (
            "update-content must call repo.edit() or repo.replace_topics(); "
            "a no-op implementation fails here"
        )
