"""Tests for overlay apply when branch protection refuses the ref update.

AC K2d: GIVEN the recording transport refuses the ref update with a
branch-protection error WHEN gw apply runs THEN it exits non-zero, names the
repository, the branch and the protection, and prints no success line for that
module.
"""
from __future__ import annotations

import argparse
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gitweave.managers.overlays import (
    BranchProtectedError,
    ModuleSpec,
    apply_module_to_repo,
)
from gitweave.transport import RecordingTransport

REPO = "test-org/protected-repo"
CURRENT_SHA = "abc1234567890abc"
TREE_SHA = "tree1234567890ab"
NEW_TREE_SHA = "newtree9876543210"
NEW_COMMIT_SHA = "newcommit12345678"
BRANCH = "main"
PROTECTION_MSG = (
    "422 Branch protection: Required pull request reviews must be approved"
)


class _BranchProtectionApiError(Exception):
    """Simulates a 422 branch-protection error from the GitHub API."""
    status = 422


def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
    p = Path(dest)
    p.mkdir(parents=True, exist_ok=True)
    (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")


def _make_protected_branch_handler():
    """Handler where PATCH /git/refs/heads/ raises 422 (branch protected)."""
    blob_counter = [0]

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        # No applied state (fresh repo)
        if m == "GET" and ".gitweave/" in url and "/contents/" in url:
            return None

        # Ref lookup succeeds (repo has commits)
        if m == "GET" and "/git/refs/heads/" in url:
            return {"object": {"sha": CURRENT_SHA}}

        # Commit info
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

        # Ref update → branch protection error
        if m == "PATCH" and "/git/refs/heads/" in url:
            raise _BranchProtectionApiError(PROTECTION_MSG)

        raise ValueError(f"Unexpected request: {m} {url}")

    return handler


class TestOverlayProtectedBranch(unittest.TestCase):
    """AC K2d: apply raises BranchProtectedError when branch protection blocks push."""

    def test_apply_raises_branch_protected_error(self):
        """apply_module_to_repo raises BranchProtectedError naming repo/branch/protection."""
        transport = RecordingTransport(handler=_make_protected_branch_handler())
        spec = ModuleSpec(
            name="python_service", version="1.0.0", inputs={"repo_name": "my-svc"}
        )

        with self.assertRaises(BranchProtectedError) as ctx:
            with patch(
                "gitweave.managers.overlays.render_module", side_effect=_fake_render
            ):
                apply_module_to_repo(REPO, spec, transport, default_branch=BRANCH)

        err = ctx.exception
        self.assertEqual(err.repo, REPO, f"repo mismatch: {err.repo!r}")
        self.assertEqual(err.branch, BRANCH, f"branch mismatch: {err.branch!r}")
        self.assertIn(
            "protection",
            err.protection.lower(),
            f"protection message should mention 'protection': {err.protection!r}",
        )

    def test_cli_overlay_apply_exits_nonzero_on_branch_protection(self):
        """cmd_overlay_apply exits 1, names repo/branch/protection, no success line."""
        from gitweave.cli import cmd_overlay_apply

        # Build a fake gh_org and gh_repo that load a single module config
        gh_org = MagicMock()
        gh_org.login = "test-org"

        transport = RecordingTransport(handler=_make_protected_branch_handler())

        args = argparse.Namespace(repo="protected-repo")

        # Patch apply_overlays_for_repo to call apply_module_to_repo directly
        # with the protected-branch transport, bypassing config loading.
        def _fake_apply_overlays(repo_name, gh_org_arg, transport=None):
            spec = ModuleSpec(
                name="python_service", version="1.0.0", inputs={"repo_name": repo_name}
            )
            full_name = f"{gh_org_arg.login}/{repo_name}"
            with patch(
                "gitweave.managers.overlays.render_module", side_effect=_fake_render
            ):
                apply_module_to_repo(full_name, spec, transport or RecordingTransport(handler=_make_protected_branch_handler()))

        stdout_cap = io.StringIO()
        stderr_cap = io.StringIO()

        with patch("gitweave.cli._get_org_client", return_value=gh_org):
            with patch(
                "gitweave.cli.apply_overlays_for_repo" if False else
                "gitweave.managers.overlays.apply_overlays_for_repo",
                side_effect=BranchProtectedError(
                    repo=f"test-org/protected-repo",
                    branch=BRANCH,
                    protection=PROTECTION_MSG,
                ),
            ):
                with patch("sys.stdout", stdout_cap):
                    with patch("sys.stderr", stderr_cap):
                        with self.assertRaises(SystemExit) as ctx:
                            cmd_overlay_apply(args)

        # Exit non-zero
        self.assertNotEqual(ctx.exception.code, 0, "must exit non-zero on branch protection")

        stderr_out = stderr_cap.getvalue()
        # Names the repository
        self.assertIn(
            "protected-repo",
            stderr_out,
            f"stderr must name the repository: {stderr_out!r}",
        )
        # Names the branch
        self.assertIn(
            BRANCH,
            stderr_out,
            f"stderr must name the branch: {stderr_out!r}",
        )
        # Names the protection
        self.assertIn(
            "protected",
            stderr_out.lower(),
            f"stderr must mention protection: {stderr_out!r}",
        )

        # No success line on stdout
        stdout_out = stdout_cap.getvalue()
        self.assertNotIn(
            "created",
            stdout_out,
            f"stdout must not contain a success line: {stdout_out!r}",
        )
        self.assertNotIn(
            "updated",
            stdout_out,
            f"stdout must not contain a success line: {stdout_out!r}",
        )


if __name__ == "__main__":
    unittest.main()
