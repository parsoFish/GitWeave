"""Tests for per-module answers-file contract — WI-13 AC K1a, K1b.

Verifies that apply_module_to_repo writes answers to
.gitweave/<module>.copier-answers.yml, NOT to root .copier-answers.yml,
and that applying a second module leaves the first module's record byte-identical.
"""

from __future__ import annotations

import base64
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from gitweave.managers.overlays import ModuleSpec, apply_module_to_repo
from gitweave.transport import RecordingTransport

BASE_URL = "https://api.github.com"
REPO = "test-org/test-repo"
CURRENT_SHA = "abc1234567890abc"
TREE_SHA = "tree1234567890ab"
NEW_TREE_SHA = "newtree9876543210"
NEW_COMMIT_SHA = "newcommit12345678"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
    p = Path(dest)
    p.mkdir(parents=True, exist_ok=True)
    (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")


def _make_handler(per_module_state: dict[str, dict | None]):
    """Fake GitHub API handler.

    per_module_state maps module_name → applied-state-dict (or None for 404).
    """
    blob_counter = [0]
    captured_tree_entries: list[list[dict]] = []  # one list per tree POST

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        # Per-module answers file GET
        if m == "GET" and "/.gitweave/" in url and url.endswith(".copier-answers.yml"):
            # Extract module name from path
            module_name = url.split("/.gitweave/")[-1].replace(".copier-answers.yml", "")
            state = per_module_state.get(module_name)
            if state is None:
                return None
            return {"content": _b64(yaml.dump(state, default_flow_style=False))}

        # Root .copier-answers.yml — always 404 (should never be read post-migration)
        if m == "GET" and url.endswith("/contents/.copier-answers.yml"):
            return None

        if m == "GET" and "/git/refs/heads/" in url:
            return {"object": {"sha": CURRENT_SHA}}

        if m == "GET" and f"/git/commits/{CURRENT_SHA}" in url:
            return {"tree": {"sha": TREE_SHA}}

        if m == "POST" and url.endswith("/git/blobs"):
            blob_counter[0] += 1
            return {"sha": f"blob{blob_counter[0]:04d}"}

        if m == "POST" and url.endswith("/git/trees"):
            entries = kwargs.get("json", {}).get("tree", [])
            captured_tree_entries.append(entries)
            return {"sha": NEW_TREE_SHA}

        if m == "POST" and url.endswith("/git/commits"):
            return {"sha": NEW_COMMIT_SHA}

        if m == "PATCH" and "/git/refs/heads/" in url:
            return {"ref": "refs/heads/main", "object": {"sha": NEW_COMMIT_SHA}}

        # AC12: explicitly reject PR opens so assert_no_pr_opens catches mutants
        if m == "POST" and url.endswith("/pulls"):
            return {"number": 1, "html_url": "https://github.com/test/pr/1"}

        raise ValueError(f"Unexpected fake-handler request: {m} {url}")

    handler.captured_tree_entries = captured_tree_entries  # type: ignore[attr-defined]
    return handler


class TestPerModuleAnswersFile(unittest.TestCase):
    """AC K1a: per-module file placement and mutual isolation."""

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_two_modules_each_get_per_module_file(self, _mock_render):
        """K1a: applying two modules writes separate .gitweave/<module>.copier-answers.yml."""
        # --- apply python_service ---
        ps_spec = ModuleSpec(
            name="python_service",
            version="2026.10.1",
            inputs={"service_name": "my_svc"},
        )
        handler_ps = _make_handler({"python_service": None})
        transport_ps = RecordingTransport(handler=handler_ps)
        result_ps = apply_module_to_repo(REPO, ps_spec, transport_ps)
        self.assertEqual(result_ps.action, "created")
        transport_ps.assert_no_pr_opens()

        # Confirm tree entry uses per-module path
        ps_entries = handler_ps.captured_tree_entries
        self.assertTrue(ps_entries, "Expected at least one tree POST for python_service")
        ps_paths = [e["path"] for entries in ps_entries for e in entries]
        self.assertIn(
            ".gitweave/python_service.copier-answers.yml",
            ps_paths,
            f"Expected .gitweave/python_service.copier-answers.yml in tree; got {ps_paths}",
        )
        self.assertNotIn(
            ".copier-answers.yml",
            ps_paths,
            "Root .copier-answers.yml must NOT be in tree after per-module migration",
        )

        # --- apply terraform_module (python_service already applied) ---
        ps_applied_state = {
            "_module_name": "python_service",
            "_module_version": "2026.10.1",
            "_answers": {"service_name": "my_svc"},
        }
        tf_spec = ModuleSpec(
            name="terraform_module",
            version="2026.10.1",
            inputs={"env": "prod"},
        )
        handler_tf = _make_handler({
            "python_service": ps_applied_state,
            "terraform_module": None,
        })
        transport_tf = RecordingTransport(handler=handler_tf)
        result_tf = apply_module_to_repo(REPO, tf_spec, transport_tf)
        self.assertEqual(result_tf.action, "created")
        transport_tf.assert_no_pr_opens()

        tf_entries = handler_tf.captured_tree_entries
        self.assertTrue(tf_entries, "Expected at least one tree POST for terraform_module")
        tf_paths = [e["path"] for entries in tf_entries for e in entries]
        self.assertIn(
            ".gitweave/terraform_module.copier-answers.yml",
            tf_paths,
            f"Expected .gitweave/terraform_module.copier-answers.yml in tree; got {tf_paths}",
        )
        self.assertNotIn(
            ".gitweave/python_service.copier-answers.yml",
            tf_paths,
            "python_service answers file must not be re-written when terraform_module is applied",
        )
        self.assertNotIn(
            ".copier-answers.yml",
            tf_paths,
            "Root .copier-answers.yml must NOT appear after terraform_module apply",
        )

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_python_service_record_byte_identical_after_terraform_module(self, _mock_render):
        """K1a: python_service answers content unchanged when terraform_module is applied."""
        ps_applied_state = {
            "_module_name": "python_service",
            "_module_version": "2026.10.1",
            "_answers": {"service_name": "my_svc"},
        }
        original_content = yaml.dump(ps_applied_state, default_flow_style=False)

        tf_spec = ModuleSpec(
            name="terraform_module",
            version="2026.10.1",
            inputs={"env": "staging"},
        )
        handler_tf = _make_handler({
            "python_service": ps_applied_state,
            "terraform_module": None,
        })
        transport_tf = RecordingTransport(handler=handler_tf)
        apply_module_to_repo(REPO, tf_spec, transport_tf)
        transport_tf.assert_no_pr_opens()

        tf_entries = handler_tf.captured_tree_entries
        tf_paths = [e["path"] for entries in tf_entries for e in entries]
        self.assertNotIn(
            ".gitweave/python_service.copier-answers.yml",
            tf_paths,
            f"python_service answers file was re-written (not byte-identical): {tf_paths}",
        )


class TestRootAnswersFileMutant(unittest.TestCase):
    """AC K1b: regression guard — mutant that writes to root .copier-answers.yml is detected."""

    @patch("gitweave.managers.overlays.render_module", side_effect=_fake_render)
    def test_root_answers_file_mutant(self, _mock_render):
        """K1b: correct code never writes root .copier-answers.yml.

        This test would fail if a mutant replaced the per-module path with root
        .copier-answers.yml — making it a live regression guard.
        """
        spec = ModuleSpec(
            name="python_service",
            version="1.0",
            inputs={"service_name": "svc"},
        )
        handler = _make_handler({"python_service": None})
        transport = RecordingTransport(handler=handler)
        apply_module_to_repo(REPO, spec, transport)

        all_entries = handler.captured_tree_entries
        all_paths = [e["path"] for entries in all_entries for e in entries]

        # Guard: root .copier-answers.yml must NOT be written
        self.assertNotIn(
            ".copier-answers.yml",
            all_paths,
            (
                "Mutant detected: root .copier-answers.yml written instead of "
                ".gitweave/python_service.copier-answers.yml — "
                f"tree paths: {all_paths}"
            ),
        )
        # And per-module path must be present (confirm correct code ran)
        self.assertIn(
            ".gitweave/python_service.copier-answers.yml",
            all_paths,
            f"Per-module answers file missing from tree; got {all_paths}",
        )
        # AC12: no PR should have been opened
        transport.assert_no_pr_opens()


if __name__ == "__main__":
    unittest.main()
