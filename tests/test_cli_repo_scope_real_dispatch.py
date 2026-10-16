"""B4: Real CLI dispatch through gitweave.cli.main() enforces repo-scope policy.

No synthetic subprocess, no direct call to the self_serve function.
gitweave.cli.main() is called in-process with sys.argv set; auth and policy
are patched at the CLI boundary only.

For each of update-content, add-exception, list-exceptions:
  - denied repo → non-zero exit, stderr names allowed_repo_patterns,
    no write call on the stubbed client, check_permission received repo_name
  - allowed repo → exit 0
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

from gitweave.policy import PolicyDenied

# ---------------------------------------------------------------------------
# Shared test policy
# ---------------------------------------------------------------------------

_TEAM = "myteam"
_ALLOWED_REPO = "allowed-repo"
_DENIED_REPO = "other-team-repo"
_DENIED_MSG = (
    f"repo_name '{_DENIED_REPO}' does not match any pattern in "
    f"{_TEAM}.allowed_repo_patterns: ['allowed-*']"
)

_POLICY = {
    "teams": [
        {
            "slug": _TEAM,
            "allowed_request_types": ["content-update", "policy-exception"],
            "allowed_repo_patterns": ["allowed-*"],
            "allowed_exceptions": ["skip-codeowners"],
            "allowed_content_settings": ["description"],
        }
    ]
}


def _make_gh_org():
    org = MagicMock()
    org.login = "my-org"
    org._requester.requestJsonAndCheck = MagicMock(return_value=({}, []))
    repo = MagicMock()
    org.get_repo.return_value = repo
    return org


def _fake_auth(gh_org):
    return gh_org, _POLICY, "alice"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_main_via_dispatch(argv: list[str], gh_org) -> tuple[int, str]:
    """Call gitweave.cli.main() in-process; return (exit_code, stderr_text)."""
    with (
        patch("sys.argv", argv),
        patch("gitweave.cli._self_serve_auth", return_value=_fake_auth(gh_org)),
        pytest.raises(SystemExit) as exc_info,
    ):
        import importlib
        import gitweave.cli as cli_mod
        importlib.reload(cli_mod)  # reload to pick up patched argv
        # Actually call main from the patched module context
        pass

    # Instead: call main without reload (argv is patched via sys.argv)
    return exc_info.value.code, ""


def _dispatch(argv: list[str], gh_org) -> tuple[int, str]:
    """Dispatch main() in-process and capture exit code + stderr."""
    import io
    import contextlib

    stderr_buf = io.StringIO()
    exit_code = 0
    with (
        patch("sys.argv", argv),
        patch("gitweave.cli._self_serve_auth", return_value=_fake_auth(gh_org)),
        contextlib.redirect_stderr(stderr_buf),
    ):
        with pytest.raises(SystemExit) as exc_info:
            from gitweave.cli import main
            main()
        exit_code = exc_info.value.code

    return exit_code, stderr_buf.getvalue()


# ---------------------------------------------------------------------------
# B4 — update-content via real dispatch
# ---------------------------------------------------------------------------


class TestUpdateContentRealDispatch:
    """gitweave.cli.main() update-content enforces repo scope."""

    def test_denied_repo_exits_nonzero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "update-content",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--setting", "description", "--value", "v"],
            gh_org,
        )
        assert exit_code != 0

    def test_denied_repo_stderr_names_allowed_repo_patterns(self, capsys):
        gh_org = _make_gh_org()
        _, stderr = _dispatch(
            ["gw", "self-serve", "update-content",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--setting", "description", "--value", "v"],
            gh_org,
        )
        captured = capsys.readouterr()
        combined = stderr + captured.err
        assert "allowed_repo_patterns" in combined, (
            f"Expected 'allowed_repo_patterns' in stderr. Got: {combined!r}"
        )

    def test_denied_repo_makes_no_write_call(self, capsys):
        gh_org = _make_gh_org()
        _dispatch(
            ["gw", "self-serve", "update-content",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--setting", "description", "--value", "v"],
            gh_org,
        )
        gh_org.get_repo.assert_not_called()

    def test_denied_repo_check_permission_received_repo_name(self):
        gh_org = _make_gh_org()
        calls_seen = []

        real_check = __import__(
            "gitweave.policy", fromlist=["check_permission"]
        ).check_permission

        def capturing_check(*args, **kwargs):
            calls_seen.append((args, kwargs))
            return real_check(*args, **kwargs)

        with patch("gitweave.self_serve.update_content.check_permission", side_effect=capturing_check):
            _dispatch(
                ["gw", "self-serve", "update-content",
                 "--team", _TEAM, "--repo", _DENIED_REPO,
                 "--setting", "description", "--value", "v"],
                gh_org,
            )

        assert calls_seen, "check_permission was never called"
        _, kwargs = calls_seen[0]
        assert kwargs.get("repo_name") == _DENIED_REPO, (
            f"check_permission not called with repo_name={_DENIED_REPO!r}: {calls_seen}"
        )

    def test_allowed_repo_exits_zero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "update-content",
             "--team", _TEAM, "--repo", _ALLOWED_REPO,
             "--setting", "description", "--value", "hello"],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0 for allowed repo, got {exit_code}"


# ---------------------------------------------------------------------------
# B4 — add-exception via real dispatch
# ---------------------------------------------------------------------------


class TestAddExceptionRealDispatch:
    """gitweave.cli.main() add-exception enforces repo scope."""

    def test_denied_repo_exits_nonzero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "add-exception",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--exception", "skip-codeowners", "--reason", "r"],
            gh_org,
        )
        assert exit_code != 0

    def test_denied_repo_stderr_names_allowed_repo_patterns(self, capsys):
        gh_org = _make_gh_org()
        _, stderr = _dispatch(
            ["gw", "self-serve", "add-exception",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--exception", "skip-codeowners", "--reason", "r"],
            gh_org,
        )
        captured = capsys.readouterr()
        combined = stderr + captured.err
        assert "allowed_repo_patterns" in combined, (
            f"Expected 'allowed_repo_patterns' in stderr. Got: {combined!r}"
        )

    def test_denied_repo_makes_no_write_call(self, capsys):
        gh_org = _make_gh_org()
        _dispatch(
            ["gw", "self-serve", "add-exception",
             "--team", _TEAM, "--repo", _DENIED_REPO,
             "--exception", "skip-codeowners", "--reason", "r"],
            gh_org,
        )
        gh_org._requester.requestJsonAndCheck.assert_not_called()

    def test_denied_repo_check_permission_received_repo_name(self):
        gh_org = _make_gh_org()
        calls_seen = []

        real_check = __import__(
            "gitweave.policy", fromlist=["check_permission"]
        ).check_permission

        def capturing_check(*args, **kwargs):
            calls_seen.append((args, kwargs))
            return real_check(*args, **kwargs)

        with patch("gitweave.self_serve.exceptions.check_permission", side_effect=capturing_check):
            _dispatch(
                ["gw", "self-serve", "add-exception",
                 "--team", _TEAM, "--repo", _DENIED_REPO,
                 "--exception", "skip-codeowners", "--reason", "r"],
                gh_org,
            )

        assert calls_seen, "check_permission was never called"
        _, kwargs = calls_seen[0]
        assert kwargs.get("repo_name") == _DENIED_REPO, (
            f"check_permission not called with repo_name={_DENIED_REPO!r}: {calls_seen}"
        )

    def test_allowed_repo_exits_zero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "add-exception",
             "--team", _TEAM, "--repo", _ALLOWED_REPO,
             "--exception", "skip-codeowners", "--reason", "r"],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0 for allowed repo, got {exit_code}"


# ---------------------------------------------------------------------------
# B4 — list-exceptions via real dispatch
# ---------------------------------------------------------------------------


class TestListExceptionsRealDispatch:
    """gitweave.cli.main() list-exceptions enforces repo scope."""

    def test_denied_repo_exits_nonzero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "list-exceptions",
             "--team", _TEAM, "--repo", _DENIED_REPO],
            gh_org,
        )
        assert exit_code != 0

    def test_denied_repo_stderr_names_allowed_repo_patterns(self, capsys):
        gh_org = _make_gh_org()
        _, stderr = _dispatch(
            ["gw", "self-serve", "list-exceptions",
             "--team", _TEAM, "--repo", _DENIED_REPO],
            gh_org,
        )
        captured = capsys.readouterr()
        combined = stderr + captured.err
        assert "allowed_repo_patterns" in combined, (
            f"Expected 'allowed_repo_patterns' in stderr. Got: {combined!r}"
        )

    def test_denied_repo_makes_no_api_read(self, capsys):
        gh_org = _make_gh_org()
        _dispatch(
            ["gw", "self-serve", "list-exceptions",
             "--team", _TEAM, "--repo", _DENIED_REPO],
            gh_org,
        )
        gh_org._requester.requestJsonAndCheck.assert_not_called()

    def test_denied_repo_check_permission_received_repo_name(self):
        gh_org = _make_gh_org()
        calls_seen = []

        real_check = __import__(
            "gitweave.policy", fromlist=["check_permission"]
        ).check_permission

        def capturing_check(*args, **kwargs):
            calls_seen.append((args, kwargs))
            return real_check(*args, **kwargs)

        with patch("gitweave.self_serve.exceptions.check_permission", side_effect=capturing_check):
            _dispatch(
                ["gw", "self-serve", "list-exceptions",
                 "--team", _TEAM, "--repo", _DENIED_REPO],
                gh_org,
            )

        assert calls_seen, "check_permission was never called"
        _, kwargs = calls_seen[0]
        assert kwargs.get("repo_name") == _DENIED_REPO, (
            f"check_permission not called with repo_name={_DENIED_REPO!r}: {calls_seen}"
        )

    def test_allowed_repo_exits_zero(self, capsys):
        gh_org = _make_gh_org()
        exit_code, _ = _dispatch(
            ["gw", "self-serve", "list-exceptions",
             "--team", _TEAM, "--repo", _ALLOWED_REPO],
            gh_org,
        )
        assert exit_code == 0, f"Expected exit 0 for allowed repo, got {exit_code}"
