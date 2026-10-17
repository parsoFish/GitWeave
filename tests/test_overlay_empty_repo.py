"""Tests for overlay apply on an empty (no-commits) repository.

AC K2b: Recording transport answers 409 'Git Repository is empty' on ref lookup.
  - Real run: apply_module_to_repo bootstraps via POST /git/refs and commits tree.
  - Mutant run (bootstrap replaced with no-op): raises an exception, proving
    the bootstrap step is load-bearing.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from gitweave.managers.overlays import ModuleSpec, apply_module_to_repo
from gitweave.transport import RecordingTransport

REPO = "test-org/empty-repo"
NEW_TREE_SHA = "newtree1234567890"
NEW_COMMIT_SHA = "newcomm1234567890"


class _EmptyRepoError(Exception):
    """Simulates GitHub 409 'Git Repository is empty' response."""
    status = 409


def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
    p = Path(dest)
    p.mkdir(parents=True, exist_ok=True)
    (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")


def _make_bootstrap_handler():
    """Handler: GET /git/refs/heads/ raises 409; all bootstrap calls succeed."""
    blob_counter = [0]

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        # No applied state (fresh repo — no answers file)
        if m == "GET" and ".gitweave/" in url and "/contents/" in url:
            return None

        # Ref lookup → empty repo (409)
        if m == "GET" and "/git/refs/heads/" in url:
            raise _EmptyRepoError("409 Git Repository is empty")

        # Blob creation
        if m == "POST" and url.endswith("/git/blobs"):
            blob_counter[0] += 1
            return {"sha": f"blob{blob_counter[0]:04d}"}

        # Tree creation — must NOT include base_tree for empty repo
        if m == "POST" and url.endswith("/git/trees"):
            body = kwargs.get("json", {})
            if "base_tree" in body:
                raise AssertionError(
                    "base_tree must be absent for empty-repo initial commit; "
                    f"got base_tree={body['base_tree']!r}"
                )
            return {"sha": NEW_TREE_SHA}

        # Commit creation — must have no parents
        if m == "POST" and url.endswith("/git/commits"):
            body = kwargs.get("json", {})
            parents = body.get("parents", None)
            if parents is None or len(parents) != 0:
                raise AssertionError(
                    f"Bootstrap commit must have parents=[], got {parents!r}"
                )
            return {"sha": NEW_COMMIT_SHA}

        # Initial ref creation (POST, not PATCH)
        if m == "POST" and url.endswith("/git/refs"):
            body = kwargs.get("json", {})
            if body.get("sha") != NEW_COMMIT_SHA:
                raise AssertionError(
                    f"POST /git/refs sha mismatch: expected {NEW_COMMIT_SHA!r}, "
                    f"got {body.get('sha')!r}"
                )
            return {"ref": "refs/heads/main", "object": {"sha": NEW_COMMIT_SHA}}

        raise ValueError(f"Unexpected request in bootstrap handler: {m} {url}")

    return handler


def _make_mutant_handler():
    """Mutant handler: 409 on GET refs but POST /git/refs not handled (raises ValueError).

    Simulates a code path where bootstrap is absent. apply_module_to_repo
    should raise an exception rather than silently succeeding.
    """
    blob_counter = [0]

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        if m == "GET" and ".gitweave/" in url and "/contents/" in url:
            return None

        if m == "GET" and "/git/refs/heads/" in url:
            raise _EmptyRepoError("409 Git Repository is empty")

        if m == "POST" and url.endswith("/git/blobs"):
            blob_counter[0] += 1
            return {"sha": f"blob{blob_counter[0]:04d}"}

        if m == "POST" and url.endswith("/git/trees"):
            return {"sha": NEW_TREE_SHA}

        if m == "POST" and url.endswith("/git/commits"):
            return {"sha": NEW_COMMIT_SHA}

        # Mutant: POST /git/refs is NOT handled → raises ValueError
        raise ValueError(f"Mutant handler does not support: {m} {url}")

    return handler


class TestOverlayEmptyRepo(unittest.TestCase):
    """AC K2b: apply to an empty repository bootstraps correctly."""

    def test_real_bootstrap_commits_tree(self):
        """Real run: 409 on GET refs → POST /git/refs (not PATCH) for bootstrap."""
        transport = RecordingTransport(handler=_make_bootstrap_handler())
        spec = ModuleSpec(
            name="python_service", version="1.0.0", inputs={"repo_name": "my-svc"}
        )

        with patch("gitweave.managers.overlays.render_module", side_effect=_fake_render):
            result = apply_module_to_repo(REPO, spec, transport)

        self.assertEqual(result.action, "created")
        self.assertEqual(result.repo, REPO)

        # POST /git/refs used (not PATCH) for the initial ref creation
        ref_creates = transport.filter("POST", "*/git/refs")
        self.assertEqual(
            len(ref_creates), 1,
            "Expected exactly one POST /git/refs for empty-repo bootstrap",
        )

        # PATCH /git/refs/heads/* must NOT have been called
        ref_patches = transport.filter("PATCH", "*/git/refs/heads/*")
        self.assertEqual(
            len(ref_patches), 0,
            "PATCH /git/refs/heads/* must not be called for an empty repo",
        )

        transport.assert_no_pr_opens()

    def test_mutant_bootstrap_noop_fails(self):
        """Mutant run: without POST /git/refs handler, apply raises an exception.

        This proves the bootstrap path is load-bearing: removing it breaks the
        apply, and the error surfaces rather than silently succeeding.
        """
        transport = RecordingTransport(handler=_make_mutant_handler())
        spec = ModuleSpec(
            name="python_service", version="1.0.0", inputs={"repo_name": "my-svc"}
        )

        with self.assertRaises(Exception):
            with patch(
                "gitweave.managers.overlays.render_module", side_effect=_fake_render
            ):
                apply_module_to_repo(REPO, spec, transport)


if __name__ == "__main__":
    unittest.main()
