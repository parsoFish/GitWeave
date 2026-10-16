"""AC6: gw self-serve remove-member is registered in argparse and dispatches
through check_permission to self_serve_remove_member.
"""
from __future__ import annotations

import argparse
import pytest
from unittest.mock import MagicMock, patch

from gitweave.policy import PolicyDenied


_POLICY = {
    "teams": [
        {
            "slug": "myteam",
            "allowed_request_types": ["team-membership"],
            "allowed_repo_patterns": [],
        }
    ]
}


class TestRemoveMemberRegistered:
    """remove-member subcommand exists in the argparse tree."""

    def test_remove_member_subcommand_registered(self):
        """Parsing 'gw self-serve remove-member --team X --member Y' does not error."""
        from gitweave.cli import main
        import sys

        parser = argparse.ArgumentParser(prog="gw")
        # Re-build the parser by importing and calling the internal builder
        # (cheapest approach: just call main with --help and catch SystemExit(0))
        with pytest.raises(SystemExit) as exc:
            sys.argv = ["gw", "self-serve", "remove-member", "--help"]
            main()
        # --help exits 0
        assert exc.value.code == 0

    def test_remove_member_dispatches_through_check_permission(self, capsys):
        """remove-member handler calls check_permission (spy asserted)."""
        from gitweave.cli import cmd_self_serve_remove_member

        gh_org = MagicMock()
        args = MagicMock(team="myteam", member="bob")

        denied_msg = "team-membership not in myteam.allowed_request_types"
        with patch("gitweave.cli._self_serve_auth", return_value=(gh_org, _POLICY, "alice")), \
             patch("gitweave.self_serve.membership.check_permission",
                   side_effect=PolicyDenied(denied_msg)) as spy:
            with pytest.raises(SystemExit) as exc:
                cmd_self_serve_remove_member(args)
            assert exc.value.code != 0

        spy.assert_called_once()
        out = capsys.readouterr()
        assert denied_msg in out.err

    def test_remove_member_exits_nonzero_on_policy_denied(self):
        """Handler exits non-zero when policy denies."""
        from gitweave.cli import cmd_self_serve_remove_member

        gh_org = MagicMock()
        args = MagicMock(team="myteam", member="bob")

        with patch("gitweave.cli._self_serve_auth", return_value=(gh_org, _POLICY, "alice")), \
             patch("gitweave.self_serve.membership.check_permission",
                   side_effect=PolicyDenied("denied")):
            with pytest.raises(SystemExit) as exc:
                cmd_self_serve_remove_member(args)
            assert exc.value.code != 0

    def test_remove_member_does_not_write_on_denial(self):
        """remove_membership is never called when check_permission denies."""
        from gitweave.cli import cmd_self_serve_remove_member

        gh_org = MagicMock()
        args = MagicMock(team="myteam", member="bob")

        with patch("gitweave.cli._self_serve_auth", return_value=(gh_org, _POLICY, "alice")), \
             patch("gitweave.self_serve.membership.check_permission",
                   side_effect=PolicyDenied("denied")):
            with pytest.raises(SystemExit):
                cmd_self_serve_remove_member(args)

        gh_org.get_team_by_slug.assert_not_called()
