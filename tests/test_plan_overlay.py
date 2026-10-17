"""tests/test_plan_overlay.py — offline tests for gw plan overlay awareness.

Fixture format
--------------
The offline fixture is a JSON dict with the following structure::

    {
        "repos": [
            {
                "name": "repo-a",
                "overlay": null
            },
            {
                "name": "repo-b",
                "overlay": {
                    "_module_name": "python_service",
                    "_module_version": "20261017.0",
                    "_answers": {"service_name": "svc_b"}
                }
            }
        ]
    }

Keys present in each repo entry:
- ``name`` (str): canonical repository name matching ``metadata.name`` in
  ``config/repos/<name>.yaml``.
- ``overlay`` (dict | null): content of ``.copier-answers.yml`` as read from
  the repository at fixture-capture time; ``null`` means the file was not
  found (no module has been applied yet).

How repos are represented:
- Only repos with an ``overlay`` key are included in overlay planning.
- Standard ``repos`` entries without an ``overlay`` key are handled by the
  existing plan diff engine (create/delete/unchanged).

How applied-module state is recorded (in ``overlay`` dict):
- ``_module_name`` (str): name of the copier module that was applied.
- ``_module_version`` (str): CalVer version string of the applied module.
- ``_answers`` (dict): copier answers provided at apply time.
"""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from gitweave.plan import plan, PlanResult


REPO_ROOT = pathlib.Path(__file__).parent.parent


def _overlay_fixture(tmp_path: pathlib.Path, repos: list[dict]) -> str:
    """Write a minimal overlay fixture to *tmp_path* and return its path."""
    fixture = {"repos": repos}
    p = tmp_path / "overlay-fixture.json"
    p.write_text(json.dumps(fixture))
    return str(p)


def _minimal_cfg() -> dict:
    return {
        "org_settings": {
            "description": "",
            "default_repository_permission": "read",
            "web_commit_signoff_required": False,
            "members_can_create_repositories": True,
        },
        "teams": [],
        "repos": [],
        "rulesets": [],
    }


class TestPlanOverlay:
    """Tests for overlay-aware plan output (AC1, AC4)."""

    def test_plan_lists_files_for_repo_without_modules(self, tmp_path, monkeypatch):
        """AC1: fixture with no-overlay repo declaring python_service →
        plan output mentions 'would add [python_service'."""
        monkeypatch.delenv("GW_ORG", raising=False)
        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)

        # example-smoke-repo is declared in config/repos/example.yaml with
        # spec.modules: [{name: python_service}]
        repos = [
            {"name": "example-smoke-repo", "overlay": None},
        ]
        fixture_path = _overlay_fixture(tmp_path, repos)

        buf = io.StringIO()
        with patch("gitweave.plan.load_config", return_value=_minimal_cfg()):
            result = plan(fixture_path=fixture_path)
            with redirect_stdout(buf):
                result.print()

        output = buf.getvalue()
        assert "would add [python_service" in output, (
            f"Expected 'would add [python_service' in plan output, got:\n{output}"
        )

    def test_plan_unchanged_for_matching_repo(self, tmp_path, monkeypatch):
        """AC1: fixture where repo's applied state matches declared →
        plan output mentions 'unchanged'."""
        monkeypatch.delenv("GW_ORG", raising=False)
        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)

        repos = [
            {
                "name": "example-smoke-repo",
                "overlay": {
                    "_module_name": "python_service",
                    "_module_version": "20261017.0",
                    "_answers": {"service_name": "svc_example"},
                },
            },
        ]
        fixture_path = _overlay_fixture(tmp_path, repos)

        buf = io.StringIO()
        with patch("gitweave.plan.load_config", return_value=_minimal_cfg()):
            result = plan(fixture_path=fixture_path)
            with redirect_stdout(buf):
                result.print()

        output = buf.getvalue()
        assert "unchanged" in output, (
            f"Expected 'unchanged' in plan output, got:\n{output}"
        )

    def test_plan_no_overlay_section_without_fixture(self, monkeypatch):
        """AC1: plan() with no fixture → overlay section absent from output."""
        monkeypatch.delenv("GW_ORG", raising=False)
        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)

        buf = io.StringIO()
        with patch("gitweave.plan.load_config", return_value=_minimal_cfg()):
            with pytest.raises(EnvironmentError, match="GW_ORG"):
                plan()

        # Also verify: a result with no overlay_items prints no "Overlays:" header
        result = PlanResult(items=[], overlay_items=[])
        with redirect_stdout(buf):
            result.print()
        assert "Overlays:" not in buf.getvalue()

    def test_apply_overlays_py_deleted(self):
        """AC2: scripts/apply-overlays.py is not tracked by git."""
        result = subprocess.run(
            ["git", "ls-files", "scripts/apply-overlays.py"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.stdout.strip() == "", (
            "scripts/apply-overlays.py is still tracked by git; it must be deleted"
        )
