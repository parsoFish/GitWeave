"""AC4: Each gw self-serve CLI subcommand calls gitweave.policy.check_permission via spy.

Refusal message must cite the denying rule; exit non-zero; nothing written to org.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from gitweave.policy import PolicyDenied


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLICY = {
    "teams": [
        {
            "slug": "myteam",
            "allowed_request_types": ["new-repo", "content-update", "team-membership", "policy-exception"],
            "allowed_repo_patterns": ["myteam-*"],
            "allowed_exceptions": ["skip-codeowners"],
            "allowed_content_settings": ["description"],
        }
    ]
}

_DENIED_MSG = "op not in myteam.allowed_request_types"


def _fake_auth():
    gh_org = MagicMock()
    return gh_org, _POLICY, "alice"


def _run_denied(cmd_fn, args_attrs):
    """Run cmd_fn with check_permission patched to deny. Return (spy, stderr)."""
    args = MagicMock(**args_attrs)
    with patch("gitweave.cli._self_serve_auth", return_value=_fake_auth()), \
         patch("gitweave.self_serve.new_repo.check_permission",
               side_effect=PolicyDenied(_DENIED_MSG)) as sp_nr, \
         patch("gitweave.self_serve.update_content.check_permission",
               side_effect=PolicyDenied(_DENIED_MSG)) as sp_uc, \
         patch("gitweave.self_serve.membership.check_permission",
               side_effect=PolicyDenied(_DENIED_MSG)) as sp_mb, \
         patch("gitweave.self_serve.exceptions.check_permission",
               side_effect=PolicyDenied(_DENIED_MSG)) as sp_ex:
        with pytest.raises(SystemExit) as exc:
            cmd_fn(args)
        assert exc.value.code != 0, "Expected non-zero exit for denied request"
        spies = [sp_nr, sp_uc, sp_mb, sp_ex]
        called = [s for s in spies if s.called]
        return called


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckPermissionSpied:
    """Each self-serve subcommand calls check_permission; refusal cites rule."""

    def test_new_repo_calls_check_permission(self, capsys):
        from gitweave.cli import cmd_self_serve_new_repo
        called = _run_denied(cmd_self_serve_new_repo, {"team": "myteam", "name": "myteam-foo"})
        assert called, "check_permission was not called by new-repo handler"
        out = capsys.readouterr()
        assert _DENIED_MSG in out.err, f"Denial rule not cited in stderr: {out.err!r}"

    def test_update_content_calls_check_permission(self, capsys):
        from gitweave.cli import cmd_self_serve_update_content
        called = _run_denied(
            cmd_self_serve_update_content,
            {"team": "myteam", "repo": "myteam-repo", "setting": "description", "value": "test"},
        )
        assert called, "check_permission was not called by update-content handler"
        out = capsys.readouterr()
        assert _DENIED_MSG in out.err

    def test_add_member_calls_check_permission(self, capsys):
        from gitweave.cli import cmd_self_serve_add_member
        called = _run_denied(
            cmd_self_serve_add_member,
            {"team": "myteam", "member": "bob"},
        )
        assert called, "check_permission was not called by add-member handler"
        out = capsys.readouterr()
        assert _DENIED_MSG in out.err

    def test_remove_member_calls_check_permission(self, capsys):
        from gitweave.cli import cmd_self_serve_remove_member
        called = _run_denied(
            cmd_self_serve_remove_member,
            {"team": "myteam", "member": "bob"},
        )
        assert called, "check_permission was not called by remove-member handler"
        out = capsys.readouterr()
        assert _DENIED_MSG in out.err

    def test_add_exception_calls_check_permission(self, capsys):
        from gitweave.cli import cmd_self_serve_add_exception
        called = _run_denied(
            cmd_self_serve_add_exception,
            {"team": "myteam", "repo": "myteam-repo", "exception": "skip-codeowners", "reason": "urgent"},
        )
        assert called, "check_permission was not called by add-exception handler"
        out = capsys.readouterr()
        assert _DENIED_MSG in out.err

    def test_denied_does_not_write_to_org(self):
        """When policy denies, org write methods are never called."""
        from gitweave.cli import cmd_self_serve_new_repo
        gh_org = MagicMock()
        with patch("gitweave.cli._self_serve_auth", return_value=(gh_org, _POLICY, "alice")), \
             patch("gitweave.self_serve.new_repo.check_permission",
                   side_effect=PolicyDenied(_DENIED_MSG)):
            with pytest.raises(SystemExit):
                cmd_self_serve_new_repo(MagicMock(team="myteam", name="myteam-foo"))
        gh_org.create_repo.assert_not_called()
