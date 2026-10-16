"""AC7: Every self-serve CLI handler catches PolicyError (not only PolicyDenied),
exits non-zero with one-line error naming the policy file; no traceback.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from gitweave.policy import PolicyError, PolicyDenied

_POLICY_FILE = "config/policy.yaml"
_POLICY_ERR_MSG = f"Policy file not found: {_POLICY_FILE}. Create config/policy.yaml to define team permissions."


def _auth_raises_policy_error():
    """Simulate _self_serve_auth raising a non-PolicyDenied PolicyError."""
    raise PolicyError(_POLICY_ERR_MSG)


_HANDLERS = [
    ("cmd_self_serve_new_repo",      {"team": "x", "name": "x-repo"}),
    ("cmd_self_serve_update_content", {"team": "x", "repo": "x-repo", "setting": "description", "value": "v"}),
    ("cmd_self_serve_add_member",    {"team": "x", "member": "bob"}),
    ("cmd_self_serve_remove_member", {"team": "x", "member": "bob"}),
    ("cmd_self_serve_add_exception", {"team": "x", "repo": "x-repo", "exception": "skip", "reason": "r"}),
    ("cmd_self_serve_list_exceptions", {"repo": "x-repo"}),
]


class TestPolicyErrorHandling:
    """All self-serve handlers catch PolicyError and exit non-zero without traceback."""

    @pytest.mark.parametrize("cmd_name,attrs", _HANDLERS)
    def test_handler_exits_nonzero_on_policy_error(self, cmd_name, attrs, capsys):
        import gitweave.cli as cli_mod
        cmd_fn = getattr(cli_mod, cmd_name)
        args = MagicMock(**attrs)

        with patch("gitweave.cli._self_serve_auth", side_effect=_auth_raises_policy_error):
            with pytest.raises(SystemExit) as exc:
                cmd_fn(args)
            assert exc.value.code != 0, \
                f"{cmd_name} did not exit non-zero on PolicyError"

    @pytest.mark.parametrize("cmd_name,attrs", _HANDLERS)
    def test_handler_names_policy_file_in_stderr(self, cmd_name, attrs, capsys):
        import gitweave.cli as cli_mod
        cmd_fn = getattr(cli_mod, cmd_name)
        args = MagicMock(**attrs)

        with patch("gitweave.cli._self_serve_auth", side_effect=_auth_raises_policy_error):
            with pytest.raises(SystemExit):
                cmd_fn(args)

        out = capsys.readouterr()
        assert "policy" in out.err.lower() or _POLICY_FILE in out.err, \
            f"{cmd_name} stderr did not mention policy file: {out.err!r}"

    @pytest.mark.parametrize("cmd_name,attrs", _HANDLERS)
    def test_handler_one_line_error_no_traceback(self, cmd_name, attrs, capsys):
        """Output must be a single line with no 'Traceback' header."""
        import gitweave.cli as cli_mod
        cmd_fn = getattr(cli_mod, cmd_name)
        args = MagicMock(**attrs)

        with patch("gitweave.cli._self_serve_auth", side_effect=_auth_raises_policy_error):
            with pytest.raises(SystemExit):
                cmd_fn(args)

        out = capsys.readouterr()
        assert "Traceback" not in out.err, \
            f"{cmd_name} printed a traceback on PolicyError"
        lines = [l for l in out.err.splitlines() if l.strip()]
        assert len(lines) == 1, \
            f"{cmd_name} stderr was not a single line: {out.err!r}"
