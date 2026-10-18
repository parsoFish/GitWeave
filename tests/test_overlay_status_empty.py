"""Tests for gw overlay status on a repository with no .gitweave/ directory.

AC K2c: GIVEN a repository with no .gitweave/ directory (contents API 404)
WHEN gw overlay status <repo> runs
THEN it prints 'no modules applied' and exits 0 with no traceback.
"""
from __future__ import annotations

import argparse
import io
import sys
import unittest
from unittest.mock import MagicMock, patch


def _make_gh_repo_no_gitweave() -> MagicMock:
    """Return a fake PyGitHub Repository where get_contents('.gitweave') raises 404."""
    gh_repo = MagicMock()
    exc = Exception("404 Not Found")
    exc.status = 404  # type: ignore[attr-defined]
    gh_repo.get_contents.side_effect = exc
    return gh_repo


def _make_gh_org(gh_repo: MagicMock) -> MagicMock:
    gh_org = MagicMock()
    gh_org.get_repo.return_value = gh_repo
    return gh_org


class TestOverlayStatusEmpty(unittest.TestCase):
    """AC K2c: overlay status on repo with no modules prints 'no modules applied'."""

    def test_status_no_gitweave_prints_no_modules_applied(self):
        """CLI exits 0 and prints 'no modules applied' for a fresh (no modules) repo."""
        from gitweave.cli import cmd_overlay_status

        gh_repo = _make_gh_repo_no_gitweave()
        gh_org = _make_gh_org(gh_repo)
        args = argparse.Namespace(repo="empty-repo")

        captured = io.StringIO()
        with patch("gitweave.cli._get_org_client", return_value=gh_org):
            with patch("sys.stdout", captured):
                with self.assertRaises(SystemExit) as ctx:
                    cmd_overlay_status(args)

        self.assertEqual(ctx.exception.code, 0, "exit code must be 0")
        output = captured.getvalue()
        self.assertIn(
            "no modules applied",
            output.lower(),
            f"Expected 'no modules applied' in stdout, got: {output!r}",
        )

    def test_status_no_gitweave_no_traceback(self):
        """No exception or traceback propagates when .gitweave/ is absent."""
        from gitweave.cli import cmd_overlay_status

        gh_repo = _make_gh_repo_no_gitweave()
        gh_org = _make_gh_org(gh_repo)
        args = argparse.Namespace(repo="empty-repo")

        stderr_captured = io.StringIO()
        with patch("gitweave.cli._get_org_client", return_value=gh_org):
            with patch("sys.stdout", io.StringIO()):
                with patch("sys.stderr", stderr_captured):
                    with self.assertRaises(SystemExit) as ctx:
                        cmd_overlay_status(args)

        self.assertEqual(ctx.exception.code, 0)
        stderr_out = stderr_captured.getvalue()
        self.assertNotIn(
            "Traceback",
            stderr_out,
            f"Unexpected traceback in stderr: {stderr_out!r}",
        )
        self.assertNotIn(
            "Exception",
            stderr_out,
            f"Unexpected exception text in stderr: {stderr_out!r}",
        )


if __name__ == "__main__":
    unittest.main()
