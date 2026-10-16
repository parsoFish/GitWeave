"""Tests for gw self-serve CLI subcommands (WI-7)."""

import json
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from gitweave.auth import CallerTokenRequiredError
from gitweave.policy import PolicyDenied


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GW_ORG = "test-org"

_AUTH_PATCHES = {
    "gitweave.cli.get_caller_token": lambda: "tok-123",
    "gitweave.cli.get_github_client": None,  # replaced per-test with MagicMock
    "gitweave.cli.resolve_caller_login": lambda _t: "alice",
    "gitweave.cli.PolicyLoader": None,  # replaced per-test
}


def _make_gh_org_mock():
    org = MagicMock()
    org.login = _GW_ORG
    return org


def _gh_client_factory(gh_org):
    """Return a patched get_github_client that yields gh_org."""
    gh = MagicMock()
    gh.get_organization.return_value = gh_org
    return lambda: gh


def _policy_loader_factory(policy_dict):
    loader = MagicMock()
    loader.return_value.load.return_value = policy_dict
    return loader


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSelfServeCLI:
    """AC1–AC7: gw self-serve subcommand wiring."""

    # -- AC1: new-repo -------------------------------------------------------

    def test_new_repo_subcommand_registered(self, capsys, monkeypatch):
        """AC1: new-repo dispatches to self_serve_new_repo and exits 0."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": [{"slug": "alpha", "allowed_request_types": ["new-repo"]}]}
        result_val = {"created": True}

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_new_repo", return_value=result_val
            ) as mock_fn,
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "alpha", "--name", "my-repo"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_fn.assert_called_once_with("alpha", "my-repo", gh_org, policy, "alice")
        captured = capsys.readouterr()
        assert json.loads(captured.out) == result_val

    # -- AC2: update-content -------------------------------------------------

    def test_update_content_dispatches(self, capsys, monkeypatch):
        """AC2: update-content dispatches with correct args and exits 0."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}
        result_val = {"applied": True}

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_update_content", return_value=result_val
            ) as mock_fn,
            patch(
                "sys.argv",
                [
                    "gw",
                    "self-serve",
                    "update-content",
                    "--team",
                    "alpha",
                    "--repo",
                    "my-repo",
                    "--setting",
                    "topics",
                    "--value",
                    "a,b",
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_fn.assert_called_once_with(
            "alpha", "my-repo", "topics", ["a", "b"], gh_org, policy, "alice"
        )

    # -- AC3: add-member -----------------------------------------------------

    def test_add_member_dispatches(self, capsys, monkeypatch):
        """AC3: add-member dispatches with correct args and exits 0."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}
        result_val = {"applied": True}

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_add_member", return_value=result_val
            ) as mock_fn,
            patch(
                "sys.argv",
                [
                    "gw",
                    "self-serve",
                    "add-member",
                    "--team",
                    "alpha",
                    "--member",
                    "bob",
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_fn.assert_called_once_with("alpha", "bob", gh_org, policy, "alice")

    # -- AC4: add-exception --------------------------------------------------

    def test_add_exception_dispatches(self, capsys, monkeypatch):
        """AC4: add-exception dispatches with correct args and exits 0."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}
        result_val = {"recorded": True}

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_add_exception", return_value=result_val
            ) as mock_fn,
            patch(
                "sys.argv",
                [
                    "gw",
                    "self-serve",
                    "add-exception",
                    "--team",
                    "alpha",
                    "--repo",
                    "my-repo",
                    "--exception",
                    "no-branch-protection",
                    "--reason",
                    "legacy setup",
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_fn.assert_called_once_with(
            "alpha", "my-repo", "no-branch-protection", "legacy setup", gh_org, policy, "alice"
        )

    # -- AC5: list-exceptions ------------------------------------------------

    def test_list_exceptions_dispatches(self, capsys, monkeypatch):
        """AC5: list-exceptions prints JSON result and exits 0."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}
        result_val = [{"exception": "no-branch-protection", "reason": "legacy"}]

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_list_exceptions", return_value=result_val
            ) as mock_fn,
            patch(
                "sys.argv",
                ["gw", "self-serve", "list-exceptions", "--repo", "my-repo"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_fn.assert_called_once_with("my-repo", gh_org)
        captured = capsys.readouterr()
        assert json.loads(captured.out) == result_val

    # -- AC6: CallerTokenRequiredError ---------------------------------------

    def test_caller_token_required_exits_nonzero(self, capsys, monkeypatch):
        """AC6: CallerTokenRequiredError → stderr with 'caller-token-required', exit non-zero."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)

        with (
            patch(
                "gitweave.cli.get_caller_token",
                side_effect=CallerTokenRequiredError("no token set"),
            ),
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "alpha", "--name", "r"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code != 0
        captured = capsys.readouterr()
        assert "caller-token-required" in captured.err

    # -- AC7: PolicyDenied ---------------------------------------------------

    def test_policy_denied_exits_nonzero(self, capsys, monkeypatch):
        """AC7: PolicyDenied → stderr with denial message, exit non-zero."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "gitweave.cli.self_serve_new_repo",
                side_effect=PolicyDenied("rule: new-repo denied for team alpha"),
            ),
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "alpha", "--name", "r"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code != 0
        captured = capsys.readouterr()
        assert "new-repo denied for team alpha" in captured.err


class TestSelfServeCLIPermissionGate:
    """AC5: Real CLI path calls check_permission(); per-repo authorisation enforced."""

    # ------------------------------------------------------------------
    # AC5-a: check_permission() is called on the new-repo CLI path
    # ------------------------------------------------------------------

    def test_new_repo_real_path_calls_check_permission(self, capsys, monkeypatch):
        """check_permission is invoked (via self_serve_new_repo) on the real CLI path.

        Does NOT mock self_serve_new_repo — goes through the real function,
        only mocking the GitHub API.
        """
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        # Allow the request so check_permission returns True
        policy = {
            "teams": [
                {
                    "slug": "alpha",
                    "allowed_request_types": ["new-repo"],
                    "allowed_repo_patterns": ["allowed-*"],
                }
            ]
        }
        gh_org.create_repo = MagicMock(return_value=MagicMock())

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch("gitweave.self_serve.new_repo.check_permission") as mock_cp,
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "alpha", "--name", "allowed-svc"],
            ),
        ):
            mock_cp.return_value = True
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code == 0
        mock_cp.assert_called_once_with(policy, "alpha", "new-repo", repo_name="allowed-svc")

    def test_new_repo_real_path_policy_violation_exits_nonzero(self, capsys, monkeypatch):
        """CLI exits non-zero and names the policy rule when check_permission denies."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        # Policy that forbids the name pattern
        policy = {
            "teams": [
                {
                    "slug": "alpha",
                    "allowed_request_types": ["new-repo"],
                    "allowed_repo_patterns": ["allowed-*"],
                }
            ]
        }

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "alpha", "--name", "forbidden-repo"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code != 0
        captured = capsys.readouterr()
        # check_permission raises PolicyDenied naming allowed_repo_patterns
        assert any(kw in captured.err for kw in ("allowed_repo_patterns", "pattern", "policy"))

    def test_team_not_in_policy_exits_nonzero(self, capsys, monkeypatch):
        """CLI exits non-zero when the team has no entry in policy."""
        monkeypatch.setenv("GW_ORG", _GW_ORG)
        gh_org = _make_gh_org_mock()
        policy = {"teams": []}  # no teams declared

        with (
            patch("gitweave.cli.get_caller_token", return_value="tok"),
            patch("gitweave.cli.get_github_client", _gh_client_factory(gh_org)),
            patch("gitweave.cli.resolve_caller_login", return_value="alice"),
            patch("gitweave.cli.PolicyLoader", _policy_loader_factory(policy)),
            patch(
                "sys.argv",
                ["gw", "self-serve", "new-repo", "--team", "unknown-team", "--name", "r"],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                from gitweave.cli import main
                main()

        assert exc.value.code != 0
        captured = capsys.readouterr()
        assert "unknown-team" in captured.err
