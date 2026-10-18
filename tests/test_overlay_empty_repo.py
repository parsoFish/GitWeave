"""Tests for overlay apply on an empty (no-commits) repository.

AC K2b: Recording transport answers 409 'Git Repository is empty' on ref lookup.
  - Real run: apply_module_to_repo bootstraps via Contents API (PUT per file).
  - Mutant run (bootstrap replaced with no-op): raises an exception, proving
    the bootstrap step is load-bearing.

GitHub's Git Database API (/git/blobs, /git/trees, /git/commits, /git/refs)
returns 409 for any repository that has no git objects yet (truly empty — not
just "no HEAD branch").  The overlay engine therefore switches to the Contents
API (PUT /repos/{owner}/{repo}/contents/{path}) which works on empty repos and
creates the initial commit automatically.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from gitweave.managers.overlays import (
    ModuleSpec,
    RepositoryNotFoundError,
    apply_module_to_repo,
)
from gitweave.transport import RecordingTransport

REPO = "test-org/empty-repo"
BOOTSTRAP_COMMIT_SHA = "bootstrapcommit1234"


class _EmptyRepoError(Exception):
    """Simulates GitHub 409 'Git Repository is empty' response."""
    status = 409


def _fake_render(name: str, dest: str, data: dict | None = None) -> None:
    p = Path(dest)
    p.mkdir(parents=True, exist_ok=True)
    (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")


def _make_bootstrap_handler():
    """Handler: GET /git/refs/heads/ raises 409; Contents API PUT calls succeed."""

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        # No applied state (fresh repo — no answers file)
        if m == "GET" and ".gitweave/" in url and "/contents/" in url:
            return None

        # Ref lookup → empty repo (409); all git database API returns 409
        if m == "GET" and "/git/refs/heads/" in url:
            raise _EmptyRepoError("409 Git Repository is empty")

        # Contents API bootstrap — PUT /repos/{owner}/{repo}/contents/{path}
        if m == "PUT" and "/contents/" in url:
            return {"content": {}, "commit": {"sha": BOOTSTRAP_COMMIT_SHA}}

        raise ValueError(f"Unexpected request in bootstrap handler: {m} {url}")

    return handler


def _make_mutant_handler():
    """Mutant handler: 409 on GET refs; PUT /contents/ raises ValueError.

    Simulates a broken bootstrap path where file creation is absent.
    apply_module_to_repo must raise rather than silently succeeding.
    """

    def handler(method: str, url: str, **kwargs):
        m = method.upper()

        if m == "GET" and ".gitweave/" in url and "/contents/" in url:
            return None

        if m == "GET" and "/git/refs/heads/" in url:
            raise _EmptyRepoError("409 Git Repository is empty")

        # Mutant: Contents API PUT is not handled → raises ValueError
        raise ValueError(f"Mutant handler does not support: {m} {url}")

    return handler


class TestOverlayEmptyRepo(unittest.TestCase):
    """AC K2b: apply to an empty repository bootstraps correctly."""

    def test_real_bootstrap_commits_tree(self):
        """Real run: 409 on GET refs → Contents API PUT per file (not Git DB API)."""
        transport = RecordingTransport(handler=_make_bootstrap_handler())
        spec = ModuleSpec(
            name="python_service", version="1.0.0", inputs={"repo_name": "my-svc"}
        )

        with patch("gitweave.managers.overlays.render_module", side_effect=_fake_render):
            result = apply_module_to_repo(REPO, spec, transport)

        self.assertEqual(result.action, "created")
        self.assertEqual(result.repo, REPO)

        # Contents API PUT must have been called (one per rendered file)
        contents_puts = transport.filter("PUT", "*/contents/*")
        self.assertGreater(
            len(contents_puts), 0,
            "Expected at least one PUT /repos/{repo}/contents/{path} for empty-repo bootstrap",
        )

        # Git Database API (blobs/refs) must NOT have been called
        blob_creates = transport.filter("POST", "*/git/blobs")
        self.assertEqual(
            len(blob_creates), 0,
            "POST /git/blobs must not be called for an empty repo (returns 409 live)",
        )
        ref_creates = transport.filter("POST", "*/git/refs")
        self.assertEqual(
            len(ref_creates), 0,
            "POST /git/refs must not be called; Contents API manages branch creation",
        )

        transport.assert_no_pr_opens()

    def test_mutant_bootstrap_noop_fails(self):
        """Mutant run: without Contents API PUT handler, apply raises an exception.

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


class TestAnswersFileWrittenLast(unittest.TestCase):
    """AC16: module answers file is written last so partial failures don't record the module."""

    def test_answers_last_in_bootstrap_contents_puts(self):
        """AC16: for empty repos (Contents API path), answers file PUT comes after all other files."""
        put_order: list[str] = []

        def handler(method: str, url: str, **kwargs):
            m = method.upper()

            # No applied state (fresh repo)
            if m == "GET" and ".gitweave/" in url and "/contents/" in url:
                return None

            # Ref lookup → empty repo (409)
            if m == "GET" and "/git/refs/heads/" in url:
                raise _EmptyRepoError("409 Git Repository is empty")

            # Contents API bootstrap — record PUT order
            if m == "PUT" and "/contents/" in url:
                path = url.split("/contents/", 1)[-1]
                put_order.append(path)
                return {"content": {}, "commit": {"sha": "sha-" + path[:8]}}

            raise ValueError(f"Unexpected request: {m} {url}")

        def _multi_file_render(name: str, dest: str, data: dict | None = None) -> None:
            p = Path(dest)
            p.mkdir(parents=True, exist_ok=True)
            (p / "README.md").write_text(f"# {name}\n", encoding="utf-8")
            (p / "setup.py").write_text("# setup\n", encoding="utf-8")

        transport = RecordingTransport(handler=handler)
        spec = ModuleSpec(
            name="python_service", version="1.0.0", inputs={"repo_name": "svc"}
        )

        with patch("gitweave.managers.overlays.render_module", side_effect=_multi_file_render):
            result = apply_module_to_repo(REPO, spec, transport)

        self.assertEqual(result.action, "created")
        self.assertGreater(len(put_order), 0, "Expected at least one PUT call")

        # The answers file must be last
        answers_path = ".gitweave/python_service.copier-answers.yml"
        self.assertIn(answers_path, put_order, f"Answers file not found in PUT order: {put_order}")
        self.assertEqual(
            put_order[-1],
            answers_path,
            f"Answers file must be the LAST PUT; actual order: {put_order}",
        )


class TestRepositoryNotFoundError(unittest.TestCase):
    """AC17: transport returning None on ref lookup → RepositoryNotFoundError, not TypeError."""

    def test_none_ref_raises_repository_not_found_not_type_error(self):
        """GIVEN a transport whose every response is None (repo 404)
        WHEN apply_module_to_repo runs
        THEN it raises RepositoryNotFoundError, not TypeError.
        """
        def _all_none_handler(method, url, **kwargs):
            return None

        transport = RecordingTransport(handler=_all_none_handler)
        spec = ModuleSpec(name="python_service", version="1.0.0", inputs={})

        with patch("gitweave.managers.overlays.render_module", side_effect=_fake_render):
            with self.assertRaises(RepositoryNotFoundError) as ctx:
                apply_module_to_repo(REPO, spec, transport)

        self.assertIn(REPO, str(ctx.exception))

    def test_none_ref_does_not_raise_type_error(self):
        """Confirm TypeError is NOT the error when ref response is None."""
        def _all_none_handler(method, url, **kwargs):
            return None

        transport = RecordingTransport(handler=_all_none_handler)
        spec = ModuleSpec(name="python_service", version="1.0.0", inputs={})

        with patch("gitweave.managers.overlays.render_module", side_effect=_fake_render):
            try:
                apply_module_to_repo(REPO, spec, transport)
            except TypeError:
                self.fail("apply_module_to_repo raised TypeError instead of RepositoryNotFoundError")
            except RepositoryNotFoundError:
                pass  # expected


if __name__ == "__main__":
    unittest.main()
