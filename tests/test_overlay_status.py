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


def _make_gh_repo(applied: dict | None):
    """Return a fake PyGitHub Repository object.

    If *applied* is None, get_contents raises a GithubException(404).
    Otherwise returns a ContentFile with decoded_content set.
    """
    gh_repo = MagicMock()
    if applied is None:
        exc = Exception("404 Not Found")
        exc.status = 404  # type: ignore[attr-defined]
        gh_repo.get_contents.side_effect = exc
    else:
        content_bytes = yaml.dump(applied, default_flow_style=False).encode("utf-8")
        content_file = MagicMock()
        content_file.decoded_content = content_bytes
        gh_repo.get_contents.return_value = content_file
    return gh_repo


class TestOverlayStatus(unittest.TestCase):
    def test_status_prints_module_name_version_inputs(self):
        """AC1: with .copier-answers.yml present, output shows name, version, inputs."""
        applied = {
            "_module_name": "python_service",
            "_module_version": "1.2.3",
            "_answers": {"repo_name": "my-svc", "owner": "team-a"},
        }
        gh_repo = _make_gh_repo(applied)
        modules = get_overlay_status(gh_repo)

        self.assertEqual(len(modules), 1)
        m = modules[0]
        self.assertEqual(m["name"], "python_service")
        self.assertEqual(m["version"], "1.2.3")
        self.assertEqual(m["inputs"], {"repo_name": "my-svc", "owner": "team-a"})

    def test_status_no_answers_file_prints_none_applied(self):
        """AC2: with no .copier-answers.yml, get_overlay_status returns empty list."""
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


if __name__ == "__main__":
    unittest.main()
