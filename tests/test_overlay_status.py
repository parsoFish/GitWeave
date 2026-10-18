"""Tests for gw overlay status — .copier-answers.yml read-back via API.

Uses unittest.mock to fake PyGitHub objects.
Does NOT inherit any GW_* autouse fixtures — unit tests only.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

import yaml

from gitweave.managers.overlays import get_overlay_status


def _make_content_file(applied: dict) -> MagicMock:
    """Return a fake PyGitHub ContentFile for a .copier-answers.yml entry."""
    content_bytes = yaml.dump(applied, default_flow_style=False).encode("utf-8")
    content_file = MagicMock()
    content_file.decoded_content = content_bytes
    content_file.path = f".gitweave/{applied['_module_name']}.copier-answers.yml"
    return content_file


def _make_gh_repo(applied_list: list[dict] | None):
    """Return a fake PyGitHub Repository object.

    If *applied_list* is None, get_contents(".gitweave") raises 404.
    Otherwise returns a list of ContentFile mocks for each applied module.
    """
    gh_repo = MagicMock()
    if applied_list is None:
        exc = Exception("404 Not Found")
        exc.status = 404  # type: ignore[attr-defined]
        gh_repo.get_contents.side_effect = exc
    else:
        gh_repo.get_contents.return_value = [
            _make_content_file(a) for a in applied_list
        ]
    return gh_repo


class TestOverlayStatus(unittest.TestCase):
    def test_status_prints_module_name_version_inputs(self):
        """AC1: with .gitweave/<module>.copier-answers.yml present, returns name/version/inputs."""
        applied = {
            "_module_name": "python_service",
            "_module_version": "1.2.3",
            "_answers": {"repo_name": "my-svc", "owner": "team-a"},
        }
        gh_repo = _make_gh_repo([applied])
        modules = get_overlay_status(gh_repo)

        self.assertEqual(len(modules), 1)
        m = modules[0]
        self.assertEqual(m["name"], "python_service")
        self.assertEqual(m["version"], "1.2.3")
        self.assertEqual(m["inputs"], {"repo_name": "my-svc", "owner": "team-a"})

    def test_status_no_answers_file_prints_none_applied(self):
        """AC2: with no .gitweave/ directory, get_overlay_status returns empty list."""
        gh_repo = _make_gh_repo(None)
        modules = get_overlay_status(gh_repo)
        self.assertEqual(modules, [])

    def test_status_help_exits_zero(self):
        """AC3: gw overlay status --help exits 0."""
        result = subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "overlay", "status", "--help"],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"status", result.stdout)


class TestOverlayStatusCLIDispatch(unittest.TestCase):
    """AC21: overlay-status CLI dispatch tests — all three print literals asserted.

    Each test dispatches through cmd_overlay_status with only the GitHub API
    faked.  Three print literals kept alive:
      1. "No modules applied."          — test_cmd_overlay_status_no_modules
      2. "  {name} @ {version}"         — test_cmd_overlay_status_name_version_line
      3. "    {k}: {v}" (inputs line)   — test_cmd_overlay_status_inputs_line
    """

    def _run_cmd(self, gh_repo, repo_arg: str = "test-org/my-repo") -> tuple[int, str, str]:
        """Dispatch cmd_overlay_status; return (exit_code, stdout, stderr)."""
        import argparse, io, contextlib
        from gitweave.cli import cmd_overlay_status

        args = argparse.Namespace(repo=repo_arg)
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        exit_code = 0

        mock_org = MagicMock()
        mock_org.get_repo.return_value = gh_repo

        with (
            patch("gitweave.cli._get_org_client", return_value=mock_org),
            contextlib.redirect_stdout(stdout_buf),
            contextlib.redirect_stderr(stderr_buf),
        ):
            with self.assertRaises(SystemExit) as ctx:
                cmd_overlay_status(args)
            exit_code = ctx.exception.code

        return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_cmd_overlay_status_no_modules(self):
        """AC21 literal 1: 'No modules applied.' is printed when list is empty."""
        gh_repo = _make_gh_repo(None)
        exit_code, stdout, _ = self._run_cmd(gh_repo)
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "No modules applied.",
            stdout,
            f"Expected 'No modules applied.' in stdout; got: {stdout!r}",
        )

    def test_cmd_overlay_status_name_version_line(self):
        """AC21 literal 2: '  {name} @ {version}' line is printed for each module."""
        applied = {
            "_module_name": "python_service",
            "_module_version": "20261017.0",
            "_answers": {},
        }
        gh_repo = _make_gh_repo([applied])
        exit_code, stdout, _ = self._run_cmd(gh_repo)
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "  python_service @ 20261017.0",
            stdout,
            f"Expected '  python_service @ 20261017.0' in stdout; got: {stdout!r}",
        )

    def test_cmd_overlay_status_inputs_line(self):
        """AC21 literal 3: '    {k}: {v}' line is printed for each input key-value."""
        applied = {
            "_module_name": "python_service",
            "_module_version": "20261017.0",
            "_answers": {"service_name": "my_svc", "python_version": "3.11"},
        }
        gh_repo = _make_gh_repo([applied])
        exit_code, stdout, _ = self._run_cmd(gh_repo)
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "    service_name: my_svc",
            stdout,
            f"Expected '    service_name: my_svc' in stdout; got: {stdout!r}",
        )
        self.assertIn(
            "    python_version: 3.11",
            stdout,
            f"Expected '    python_version: 3.11' in stdout; got: {stdout!r}",
        )


if __name__ == "__main__":
    unittest.main()
