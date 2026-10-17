"""Tests for gitweave.managers.overlays — overlay apply engine.

Uses RecordingTransport with fake GitHub API handlers.
Does NOT inherit any GW_* autouse fixtures — unit tests only.
"""

from __future__ import annotations

import base64
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from gitweave.managers.overlays import ModuleSpec, OverlayApplyResult, apply_module_to_repo
from gitweave.transport import RecordingTransport

BASE_URL = "https://api.github.com"
REPO = "test-org/test-repo"
CURRENT_SHA = "abc1234567890abc"
TREE_SHA = "tree1234567890ab"
NEW_TREE_SHA = "newtree9876543210"
NEW_COMMIT_SHA = "newcommit12345678"


def _b64(text: str) -> str:
    """Base64-encode a string (GitHub API content encoding)."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _make_handler(applied_state: dict | None, module_name: str = "python_service"):
    """Return a fake GitHub API handler for overlay apply tests.

    Args:
        applied_state: dict to return for .gitweave/<module>.copier-answers.yml, or None (404).
        module_name: module name used to build the per-module path.
    """
    blob_counter = [0]
    answers_path = f".gitweave/{module_name}.copier-answers.yml"

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        # Applied state — GET contents/.gitweave/<module>.copier-answers.yml
        if m == "GET" and url.endswith(f"/contents/{answers_path}"):
            if applied_state is None:
                return None  # signals 404 / not found
            content_yaml = yaml.dump(applied_state, default_flow_style=False)
            return {"content": _b64(content_yaml)}

        # Current ref
        if m == "GET" and "/git/refs/heads/" in url:
            return {"object": {"sha": CURRENT_SHA}}

        # Commit info (tree sha)
        if m == "GET" and f"/git/commits/{CURRENT_SHA}" in url:
            return {"tree": {"sha": TREE_SHA}}

        # Blob creation
        if m == "POST" and url.endswith("/git/blobs"):
            blob_counter[0] += 1
            return {"sha": f"blob{blob_counter[0]:04d}"}

        # Tree creation
        if m == "POST" and url.endswith("/git/trees"):
            return {"sha": NEW_TREE_SHA}

        # Commit creation
        if m == "POST" and url.endswith("/git/commits"):
            return {"sha": NEW_COMMIT_SHA}

        # Ref update
        if m == "PATCH" and "/git/refs/heads/" in url:
            return {"ref": "refs/heads/main", "object": {"sha": NEW_COMMIT_SHA}}

        raise ValueError(f"Unexpected fake-handler request: {m} {url}")

    return handler


def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
    """Write minimal stub files to dest so blob creation can proceed."""
    p = Path(dest)
    p.mkdir(parents=True, exist_ok=True)
    (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    if data:
        (p / "config.py").write_text(f"CONFIG = {data!r}\n", encoding="utf-8")


class TestOverlayApply(unittest.TestCase):
    """AC1–AC4: overlay apply engine and CLI registration."""

    # ------------------------------------------------------------------
    # AC1: create branch (no applied state) → blob+tree+commit+ref, no PR
    # ------------------------------------------------------------------

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_create_branch_commits_rendered_files(self, mock_render):
        """AC1: no applied state → blob/tree/commit/ref calls; zero PR opens."""
        spec = ModuleSpec(
            name="python_service",
            version="2026.10.1",
            inputs={"service_name": "my_svc"},
        )
        transport = RecordingTransport(handler=_make_handler(applied_state=None))

        result = apply_module_to_repo(REPO, spec, transport)

        # Blob calls (rendered files + .copier-answers.yml)
        blobs = transport.filter("POST", f"*/repos/{REPO}/git/blobs")
        self.assertGreater(len(blobs), 0, "Expected at least one POST .../git/blobs call")

        # Exactly one tree, one commit, one ref update
        trees = transport.filter("POST", f"*/repos/{REPO}/git/trees")
        commits = transport.filter("POST", f"*/repos/{REPO}/git/commits")
        refs = transport.filter("PATCH", f"*/repos/{REPO}/git/refs/heads/*")
        self.assertEqual(len(trees), 1, "Expected exactly one tree creation")
        self.assertEqual(len(commits), 1, "Expected exactly one commit creation")
        self.assertEqual(len(refs), 1, "Expected exactly one ref update")

        # No PR opens
        transport.assert_no_pr_opens()

        # Result indicates creation
        self.assertEqual(result.action, "created")
        self.assertIsInstance(result, OverlayApplyResult)

        mock_render.assert_called_once_with(
            "python_service", unittest.mock.ANY, data={"service_name": "my_svc"}
        )

    # ------------------------------------------------------------------
    # AC2: unchanged — matching applied state → zero write calls
    # ------------------------------------------------------------------

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_unchanged_branch_no_write_calls(self, mock_render):
        """AC2: applied state matches declared triple → no write calls."""
        spec = ModuleSpec(
            name="python_service",
            version="2026.10.1",
            inputs={"service_name": "my_svc"},
        )
        applied = {
            "_module_name": "python_service",
            "_module_version": "2026.10.1",
            "_answers": {"service_name": "my_svc"},
        }
        transport = RecordingTransport(handler=_make_handler(applied_state=applied))

        result = apply_module_to_repo(REPO, spec, transport)

        blobs = transport.filter("POST", f"*/repos/{REPO}/git/blobs")
        trees = transport.filter("POST", f"*/repos/{REPO}/git/trees")
        commits = transport.filter("POST", f"*/repos/{REPO}/git/commits")
        refs = transport.filter("PATCH", f"*/repos/{REPO}/git/refs/heads/*")

        self.assertEqual(len(blobs), 0, "No blob calls expected for unchanged repo")
        self.assertEqual(len(trees), 0, "No tree calls expected for unchanged repo")
        self.assertEqual(len(commits), 0, "No commit calls expected for unchanged repo")
        self.assertEqual(len(refs), 0, "No ref update expected for unchanged repo")

        self.assertEqual(result.action, "unchanged")
        mock_render.assert_not_called()

    # ------------------------------------------------------------------
    # AC3: update branch — inputs differ → commit with new .copier-answers.yml
    # ------------------------------------------------------------------

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_update_branch_commits_new_inputs(self, mock_render):
        """AC3: inputs differ → new commit; .copier-answers.yml has new inputs; no PR."""
        new_inputs = {"service_name": "new_svc"}
        spec = ModuleSpec(
            name="python_service",
            version="2026.10.1",
            inputs=new_inputs,
        )
        # Applied state has same version but different inputs
        applied = {
            "_module_name": "python_service",
            "_module_version": "2026.10.1",
            "_answers": {"service_name": "old_svc"},
        }

        # Capture blob payloads to verify .copier-answers.yml content
        captured_blobs: list[dict] = []

        def capturing_handler(method: str, url: str, **kwargs):
            m = method.upper()
            if m == "POST" and url.endswith("/git/blobs"):
                captured_blobs.append(kwargs.get("json", {}))
                return {"sha": f"blob{len(captured_blobs):04d}"}
            return _make_handler(applied_state=applied)(method, url, **kwargs)

        transport = RecordingTransport(handler=capturing_handler)

        result = apply_module_to_repo(REPO, spec, transport)

        # Write calls present
        commits = transport.filter("POST", f"*/repos/{REPO}/git/commits")
        self.assertEqual(len(commits), 1, "Expected one commit for updated inputs")
        self.assertEqual(result.action, "updated")

        # Find and verify .copier-answers.yml blob
        answers_blob_found = False
        for blob_payload in captured_blobs:
            content_b64 = blob_payload.get("content", "")
            try:
                decoded = base64.b64decode(content_b64).decode("utf-8")
                doc = yaml.safe_load(decoded)
                if isinstance(doc, dict) and doc.get("_module_name") == "python_service":
                    self.assertEqual(
                        doc["_answers"],
                        new_inputs,
                        ".copier-answers.yml must record new inputs",
                    )
                    answers_blob_found = True
                    break
            except Exception:
                continue
        self.assertTrue(
            answers_blob_found,
            ".copier-answers.yml blob not found in transport call log",
        )

        # No PR opens
        transport.assert_no_pr_opens()

    # ------------------------------------------------------------------
    # AC4: CLI — gw overlay apply --help exits 0
    # ------------------------------------------------------------------

    def test_apply_help_exits_zero(self):
        """AC4: gw overlay apply --help exits 0; overlay group and apply subcommand registered."""
        proc = subprocess.run(
            [sys.executable, "-m", "gitweave.cli", "overlay", "apply", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"Expected exit 0 from --help; got {proc.returncode}\nstderr: {proc.stderr}",
        )
        # Output must mention the apply subcommand
        combined = proc.stdout + proc.stderr
        self.assertIn("apply", combined.lower())


if __name__ == "__main__":
    unittest.main()
