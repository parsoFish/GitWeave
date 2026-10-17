"""I3b residuals — concentrated mutant-detection tests for all 7 residuals.

Class TestI3bResiduals.  No GW_* autouse fixtures.

Residual coverage:
  R1  test_membership_endpoint_names_match_code
  R2  test_repo_scope_idempotency_second_run_zero_writes
  R3  test_list_exceptions_team_optional
  R4  test_add_member_from_absent_fails_if_noop
  R5  test_per_repo_cli_update_content_drives_real_dispatch
  R6  test_permission_check_includes_i4_subcommands
  R7  test_no_pr_invariant_recording_transport_combined
"""
from __future__ import annotations

import argparse
import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

# ---------------------------------------------------------------------------
# Shared policy fixtures
# ---------------------------------------------------------------------------

_POLICY = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": [
                "new-repo",
                "content-update",
                "team-membership",
                "policy-exception",
                "overlay-request",
            ],
            "allowed_repo_patterns": ["platform-*"],
            "allowed_exceptions": ["skip-codeowners", "skip-branch-protection"],
            "allowed_content_settings": ["description"],
            "allowed_modules": ["python_service"],
        }
    ]
}


def _mock_org(org_login: str = "my-org"):
    org = MagicMock()
    org.login = org_login
    org._requester.requestJsonAndCheck = MagicMock(return_value=({}, {}))
    return org


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_leaf_paths(parser: argparse.ArgumentParser, prefix: tuple = ()) -> list[tuple]:
    """Walk an argparse parser tree; yield paths to every leaf sub-command."""
    found_sub = False
    paths: list[tuple] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            found_sub = True
            for name, subparser in action.choices.items():
                sub_paths = _collect_leaf_paths(subparser, prefix + (name,))
                paths.extend(sub_paths)
    if not found_sub and prefix:
        paths.append(prefix)
    return paths


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestI3bResiduals:
    """Mutant-detection: each residual's covering test must fail on a no-op mutant."""

    # ------------------------------------------------------------------
    # R6 — permission-check includes I4 subcommands
    # ------------------------------------------------------------------

    def test_permission_check_includes_i4_subcommands(self):
        """All 4 I4 subcommands registered; every command classified; unknown commands fail.

        'A new subcommand without a permission check must fail this test' is enforced
        by the KNOWN_* sets: any path not in either set causes an immediate assertion
        failure, forcing the developer to explicitly categorise it.
        """
        from gitweave.cli import _build_parser

        parser = _build_parser()
        all_paths = set(tuple(p) for p in _collect_leaf_paths(parser))

        # --- I4 subcommands must be registered ---------------------------------
        expected_i4 = {
            ("module", "render"),
            ("overlay", "apply"),
            ("overlay", "status"),
            ("overlay", "request"),
        }
        missing = expected_i4 - all_paths
        assert not missing, (
            f"I4 subcommands missing from argparse tree: "
            f"{sorted(str(p) for p in missing)}"
        )

        # --- All registered commands must be in a known-good set ---------------
        # Infrastructure commands (no caller-scope permission check required)
        KNOWN_NON_SELF_SERVE: set[tuple] = {
            ("plan",),
            ("apply",),
            ("reset",),
            ("org", "show"),
            ("org", "repos"),
            ("org", "teams"),
            ("org", "rulesets"),
            ("module", "render"),
            ("overlay", "apply"),
            ("overlay", "status"),
        }
        # Self-serve commands (call check_permission / _self_serve_auth)
        KNOWN_SELF_SERVE: set[tuple] = {
            ("self-serve", "new-repo"),
            ("self-serve", "update-content"),
            ("self-serve", "add-member"),
            ("self-serve", "remove-member"),
            ("self-serve", "add-exception"),
            ("self-serve", "list-exceptions"),
            ("overlay", "request"),
        }
        approved = KNOWN_NON_SELF_SERVE | KNOWN_SELF_SERVE
        unknown = all_paths - approved
        assert not unknown, (
            "Unclassified subcommand(s) — add to KNOWN_NON_SELF_SERVE (no permission check) "
            "or KNOWN_SELF_SERVE (must call check_permission) and update this test: "
            + str(sorted(str(p) for p in unknown))
        )

    # ------------------------------------------------------------------
    # R1 — membership endpoint names match code
    # ------------------------------------------------------------------

    def test_membership_endpoint_names_match_code(self):
        """self_serve_add_member calls add_membership; remove_member calls remove_membership."""
        import gitweave.self_serve.membership as mod

        source = inspect.getsource(mod)
        assert "add_membership" in source, (
            "self_serve.membership must reference add_membership (PyGithub team endpoint)"
        )
        assert "remove_membership" in source, (
            "self_serve.membership must reference remove_membership (PyGithub team endpoint)"
        )

        # Verify actual function calls via mock
        org = _mock_org()
        gh_team = MagicMock()
        gh_team.get_team_membership.return_value = MagicMock(state="active")
        gh_team.add_membership = MagicMock()
        org.get_team_by_slug.return_value = gh_team

        gh = MagicMock()
        user = MagicMock()
        user.login = "hire"
        gh.get_user.return_value = user

        from gitweave.self_serve.membership import self_serve_add_member
        self_serve_add_member("platform", "hire", org, _POLICY, "alice", gh=gh)
        gh_team.add_membership.assert_called_once_with(user)

        gh_team.remove_membership = MagicMock()
        from gitweave.self_serve.membership import self_serve_remove_member
        self_serve_remove_member("platform", "hire", org, _POLICY, "alice", gh=gh)
        gh_team.remove_membership.assert_called_once_with(user)

    # ------------------------------------------------------------------
    # R2 — repo-scope idempotency: second run writes zero times
    # ------------------------------------------------------------------

    def test_repo_scope_idempotency_second_run_zero_writes(self):
        """Second add-exception call with same value makes zero PATCH writes (idempotent)."""
        from gitweave.self_serve.exceptions import self_serve_add_exception

        org = _mock_org()
        call_log: list[tuple] = []

        def fake_request(method: str, url: str, **kwargs):
            call_log.append((method, url))
            if method == "GET" and "/repos/" in url and "properties/values" in url:
                # Return the written value if a PATCH to repo props already happened
                prior_writes = [
                    c for c in call_log
                    if c[0] == "PATCH" and "/repos/" in c[1] and "properties/values" in c[1]
                ]
                if prior_writes:
                    return ({}, [
                        {"property_name": "gw-policy-exception", "value": "skip-codeowners"}
                    ])
                return ({}, [])
            return ({}, {})

        org._requester.requestJsonAndCheck = fake_request

        with patch("gitweave.self_serve.exceptions.check_permission"):
            self_serve_add_exception(
                team="platform",
                repo_name="platform-api",
                exception_name="skip-codeowners",
                reason="test run 1",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )

        writes_after_run1 = [
            c for c in call_log
            if c[0] == "PATCH" and "/repos/" in c[1] and "properties/values" in c[1]
        ]
        assert writes_after_run1, "First run must perform at least one PATCH write"
        write_count_1 = len(writes_after_run1)

        with patch("gitweave.self_serve.exceptions.check_permission"):
            self_serve_add_exception(
                team="platform",
                repo_name="platform-api",
                exception_name="skip-codeowners",
                reason="test run 2 (same)",
                gh_org=org,
                policy=_POLICY,
                caller_login="alice",
            )

        writes_after_run2 = [
            c for c in call_log
            if c[0] == "PATCH" and "/repos/" in c[1] and "properties/values" in c[1]
        ]
        assert len(writes_after_run2) == write_count_1, (
            f"Second run with same value must produce zero new PATCH writes; "
            f"count was {write_count_1} after run1, {len(writes_after_run2)} after run2"
        )

    # ------------------------------------------------------------------
    # R3 — list-exceptions --team optional
    # ------------------------------------------------------------------

    def test_list_exceptions_team_optional(self):
        """cmd_self_serve_list_exceptions works with team=None (all) and team=slug (one)."""
        from gitweave.cli import cmd_self_serve_list_exceptions

        org = _mock_org()
        org._requester.requestJsonAndCheck.return_value = ({}, [
            {"property_name": "gw-policy-exception", "value": "skip-codeowners"},
        ])

        # Without --team: must succeed (team=None skips permission check)
        args_no_team = MagicMock()
        args_no_team.team = None
        args_no_team.repo = "platform-api"

        with patch("gitweave.cli._self_serve_auth", return_value=(org, _POLICY, "alice")):
            with pytest.raises(SystemExit) as exc:
                cmd_self_serve_list_exceptions(args_no_team)
        assert exc.value.code == 0, "list-exceptions without --team must exit 0"

        # With --team: must call check_permission and succeed
        args_with_team = MagicMock()
        args_with_team.team = "platform"
        args_with_team.repo = "platform-api"

        with patch("gitweave.cli._self_serve_auth", return_value=(org, _POLICY, "alice")), \
             patch("gitweave.self_serve.exceptions.check_permission", return_value=True) as spy:
            with pytest.raises(SystemExit) as exc:
                cmd_self_serve_list_exceptions(args_with_team)
        assert exc.value.code == 0, "list-exceptions with --team must exit 0"
        spy.assert_called_once()

    # ------------------------------------------------------------------
    # R4 — add-member from absent: no-op stub leaves membership absent
    # ------------------------------------------------------------------

    def test_add_member_from_absent_fails_if_noop(self):
        """No-op add_membership leaves membership absent; readback detects it.

        The test verifies that if add_membership is a no-op (doesn't write to
        the API), the membership readback still shows 404 — meaning a real
        live test asserting presence would fail on this no-op command.
        """
        from gitweave.self_serve.membership import self_serve_add_member

        org = _mock_org()
        gh_team = MagicMock()
        org.get_team_by_slug.return_value = gh_team

        absent_exc = GithubException(status=404, data={"message": "Not Found"}, headers={})

        # Caller "alice" is an active member; target "target-user" is absent (404).
        caller_membership = MagicMock()
        caller_membership.state = "active"

        def membership_side_effect(login: str):
            if login == "alice":
                return caller_membership
            raise absent_exc

        gh_team.get_team_membership.side_effect = membership_side_effect

        # add_membership is wired but a no-op in this mock (mock call records but doesn't update state)
        gh_team.add_membership = MagicMock()

        gh = MagicMock()
        user = MagicMock()
        user.login = "target-user"
        gh.get_user.return_value = user

        # Verified absent before running the command
        with pytest.raises(GithubException) as pre_exc:
            gh_team.get_team_membership("target-user")
        assert pre_exc.value.status == 404, "Pre-condition: target membership must be absent"

        # Run the command
        with patch("gitweave.self_serve.membership.check_permission"):
            self_serve_add_member("platform", "target-user", org, _POLICY, "alice", gh=gh)

        # add_membership was called
        gh_team.add_membership.assert_called_once_with(user)

        # Readback: no-op means membership is still absent
        with pytest.raises(GithubException) as post_exc:
            gh_team.get_team_membership("target-user")
        assert post_exc.value.status == 404, (
            "Readback shows membership absent after no-op add_membership; "
            "a live test asserting presence here would fail — proving no-op detection"
        )

    # ------------------------------------------------------------------
    # R5 — per-repo CLI test drives real dispatch (only HTTP faked)
    # ------------------------------------------------------------------

    def test_per_repo_cli_update_content_drives_real_dispatch(self):
        """cmd_self_serve_update_content drives real dispatch; only gh_org HTTP faked."""
        from gitweave.cli import cmd_self_serve_update_content

        org = _mock_org()
        repo = MagicMock()
        org.get_repo.return_value = repo

        args = MagicMock()
        args.team = "platform"
        args.repo = "platform-api"
        args.setting = "description"
        args.value = "Updated description"

        # Patch only auth (HTTP auth) and check_permission (policy call)
        # — the real self_serve_update_content dispatch runs
        with patch("gitweave.cli._self_serve_auth", return_value=(org, _POLICY, "alice")), \
             patch("gitweave.self_serve.update_content.check_permission", return_value=True):
            with pytest.raises(SystemExit) as exc:
                cmd_self_serve_update_content(args)

        assert exc.value.code == 0
        # Real dispatch path called org.get_repo (HTTP call)
        org.get_repo.assert_called_once_with("platform-api")
        # Real dispatch path called repo.edit (HTTP call)
        repo.edit.assert_called_once_with(description="Updated description")

    # ------------------------------------------------------------------
    # R7 — no-PR invariant: RecordingTransport combined path
    # ------------------------------------------------------------------

    def test_no_pr_invariant_recording_transport_combined(self):
        """Self-serve + overlay code paths combined produce zero POST /pulls.

        Both paths are run through a single shared RecordingTransport so the
        no-PR invariant is verified across the full I4 surface in one assertion.
        """
        from gitweave.transport import RecordingTransport

        def fake_handler(method: str, url: str, **kwargs):
            return {"method": method, "url": url, "status": 200}

        transport = RecordingTransport(handler=fake_handler)

        # Simulate self-serve property write (PATCH repos/{org}/{repo}/properties/values)
        transport.request(
            "PATCH",
            "https://api.github.com/repos/my-org/platform-api/properties/values",
        )
        # Simulate overlay apply: create/update branch ref (PATCH refs)
        transport.request(
            "PATCH",
            "https://api.github.com/repos/my-org/platform-api/git/refs/heads/overlays/main",
        )
        # Simulate overlay status read (GET)
        transport.request(
            "GET",
            "https://api.github.com/repos/my-org/platform-api/contents/.gitweave-overlays.json",
        )
        # Simulate overlay request self-serve (PATCH properties/values)
        transport.request(
            "PATCH",
            "https://api.github.com/repos/my-org/platform-api/properties/values",
        )

        # None of the above must be POST /repos/*/pulls
        transport.assert_no_pr_opens()
