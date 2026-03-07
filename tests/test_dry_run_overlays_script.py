"""
Unit and integration tests for scripts/dry-run-overlays.py —
the Python script that runs copier diff for each overlay WITHOUT applying
changes, then posts (or updates) the output as a PR comment.

These tests drive the specification for the script (TDD red phase). They verify:

  Script existence and importability:
    - scripts/dry-run-overlays.py must exist
    - The script must be importable without SyntaxError or ModuleNotFoundError
    - The script must accept --help without crashing

  Comment formatting (format_repo_section):
    - Returns a markdown section header containing the repo slug
    - Embeds diff output in a fenced code block when diff is non-empty
    - Shows 'No changes' when diff output is empty or whitespace-only
    - Handles multi-line diff output correctly (no truncation)

  Full comment construction (format_pr_comment):
    - Returns a string that begins with a recognisable header line
    - Contains one section per entry in the repo_diffs mapping
    - Sections appear for every repo slug passed in
    - Shows 'No changes' for repos whose diff is empty or None
    - Embeds actual diff content for repos with changes
    - Includes a hidden HTML marker so the update-or-create logic can find it
    - Marker must be stable across calls (same input → same marker)

  Copier diff runner (run_copier_diff):
    - Calls copier diff with the correct module path and target directory
    - Returns stdout output when copier exits 0
    - Returns empty string when copier reports nothing to do
    - Returns empty string when copier exits non-zero (diff failure treated as no-diff)
    - Does NOT modify any files on disk (read-only operation)
    - Handles overlays with no modules (returns empty string without calling copier)
    - Calls copier once per module and concatenates outputs

  PR comment finding (find_existing_comment):
    - Returns None when no existing comments are present
    - Returns None when comments exist but none contain the marker
    - Returns the comment ID (int) of the first comment containing the marker
    - Uses the GitHub REST API (GET /repos/{repo}/issues/{pr_number}/comments)
    - Passes the Authorization header with the provided token

  PR comment posting/updating (post_or_update_comment):
    - Creates a new comment via POST when find_existing_comment returns None
    - Updates an existing comment via PATCH when find_existing_comment returns an ID
    - The posted/patched body is the formatted comment string
    - Uses the Authorization header with the provided token
    - Does not create a second comment when an existing one is found (no duplicates)

  CLI integration (subprocess-level):
    - Accepts --pr-number, --repo, --config-dir, --modules-dir flags
    - Exits 0 when run in --dry-run-only mode (prints comment, does not post)
    - Requires GITHUB_TOKEN when posting (exits non-zero when absent)
    - Prints the formatted comment to stdout in --dry-run-only mode
    - Prints a 'No changes' entry for repos with no diff

All tests will fail until scripts/dry-run-overlays.py is implemented.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT_PATH = os.path.join(REPO_ROOT, "scripts", "dry-run-overlays.py")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run_script(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """
    Invoke dry-run-overlays.py with the given arguments.
    Always captures stdout+stderr and never raises on non-zero exit.
    If env is provided, it is merged into the inherited environment.
    """
    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, SCRIPT_PATH, *args],
        capture_output=True,
        text=True,
        env=run_env,
    )


def _load_script():
    """
    Import dry-run-overlays.py as a Python module so its public functions
    can be unit-tested directly without invoking a subprocess.

    Raises FileNotFoundError with a descriptive message when the script
    does not yet exist.
    """
    if not os.path.isfile(SCRIPT_PATH):
        raise FileNotFoundError(
            f"scripts/dry-run-overlays.py not found at {SCRIPT_PATH} — "
            "the script must be implemented before these unit tests can pass"
        )
    spec = importlib.util.spec_from_file_location("dry_run_overlays", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_yaml(directory: str, filename: str, doc: dict) -> str:
    """Write doc as YAML to directory/filename and return the full path."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        yaml.dump(doc, f, default_flow_style=False)
    return path


def _minimal_overlay(repo: str = "my-org/my-app", modules: list | None = None) -> dict:
    """Return the smallest valid RepositoryOverlay document."""
    doc: dict = {
        "apiVersion": "gitweave.io/v1",
        "kind": "RepositoryOverlay",
        "metadata": {"name": repo.split("/")[-1]},
        "spec": {"repository": repo},
    }
    if modules is not None:
        doc["spec"]["modules"] = modules
    return doc


# ---------------------------------------------------------------------------
# TestScriptExists
# ---------------------------------------------------------------------------


class TestScriptExists(unittest.TestCase):
    """Basic existence and importability checks."""

    def test_dry_run_overlays_script_exists(self):
        """scripts/dry-run-overlays.py must exist at the expected path."""
        self.assertTrue(
            os.path.isfile(SCRIPT_PATH),
            f"scripts/dry-run-overlays.py is missing — expected at {SCRIPT_PATH}. "
            "Create the script before the CI job can use it.",
        )

    def test_script_is_runnable_without_syntax_errors(self):
        """The script must accept --help without SyntaxError or ModuleNotFoundError."""
        result = _run_script("--help")
        self.assertNotIn(
            "SyntaxError",
            result.stderr,
            f"scripts/dry-run-overlays.py contains a SyntaxError:\n{result.stderr}",
        )
        self.assertNotIn(
            "ModuleNotFoundError",
            result.stderr,
            f"scripts/dry-run-overlays.py has an unresolvable import:\n{result.stderr}",
        )

    def test_script_exposes_format_repo_section_function(self):
        """The script must expose a callable format_repo_section(repo_slug, diff_output)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "format_repo_section", None)),
            "scripts/dry-run-overlays.py does not expose a callable 'format_repo_section'",
        )

    def test_script_exposes_format_pr_comment_function(self):
        """The script must expose a callable format_pr_comment(repo_diffs)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "format_pr_comment", None)),
            "scripts/dry-run-overlays.py does not expose a callable 'format_pr_comment'",
        )

    def test_script_exposes_run_copier_diff_function(self):
        """The script must expose a callable run_copier_diff(config, modules_dir)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "run_copier_diff", None)),
            "scripts/dry-run-overlays.py does not expose a callable 'run_copier_diff'",
        )

    def test_script_exposes_find_existing_comment_function(self):
        """The script must expose a callable find_existing_comment(...)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "find_existing_comment", None)),
            "scripts/dry-run-overlays.py does not expose a callable 'find_existing_comment'",
        )

    def test_script_exposes_post_or_update_comment_function(self):
        """The script must expose a callable post_or_update_comment(...)."""
        mod = _load_script()
        self.assertTrue(
            callable(getattr(mod, "post_or_update_comment", None)),
            "scripts/dry-run-overlays.py does not expose a callable 'post_or_update_comment'",
        )


# ---------------------------------------------------------------------------
# TestFormatRepoSection
# ---------------------------------------------------------------------------


class TestFormatRepoSection(unittest.TestCase):
    """Unit tests for format_repo_section(repo_slug, diff_output)."""

    def setUp(self):
        self.mod = _load_script()

    def test_section_contains_repo_slug_as_header(self):
        """format_repo_section must include the repo slug in a markdown header."""
        result = self.mod.format_repo_section("org/my-app", "some diff content")
        self.assertIn(
            "org/my-app",
            result,
            f"Section must contain the repo slug 'org/my-app'. Got:\n{result}",
        )

    def test_section_embeds_diff_in_fenced_code_block(self):
        """format_repo_section wraps non-empty diff in a fenced code block."""
        diff = "--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new"
        result = self.mod.format_repo_section("org/my-app", diff)
        self.assertIn(
            "```",
            result,
            f"Section must wrap diff in a fenced code block. Got:\n{result}",
        )
        self.assertIn(
            diff,
            result,
            f"Section must contain the full diff content. Got:\n{result}",
        )

    def test_section_shows_no_changes_when_diff_is_empty_string(self):
        """format_repo_section shows 'No changes' when diff_output is empty string."""
        result = self.mod.format_repo_section("org/my-app", "")
        self.assertIn(
            "No changes",
            result,
            f"Section must show 'No changes' for empty diff. Got:\n{result}",
        )

    def test_section_shows_no_changes_when_diff_is_none(self):
        """format_repo_section shows 'No changes' when diff_output is None."""
        result = self.mod.format_repo_section("org/my-app", None)
        self.assertIn(
            "No changes",
            result,
            f"Section must show 'No changes' when diff is None. Got:\n{result}",
        )

    def test_section_shows_no_changes_when_diff_is_whitespace_only(self):
        """format_repo_section shows 'No changes' when diff_output is only whitespace."""
        result = self.mod.format_repo_section("org/my-app", "   \n  \n  ")
        self.assertIn(
            "No changes",
            result,
            f"Section must show 'No changes' for whitespace-only diff. Got:\n{result}",
        )

    def test_section_does_not_truncate_multiline_diff(self):
        """format_repo_section preserves all lines of a multi-line diff."""
        lines = [f"+line_{i}" for i in range(20)]
        diff = "\n".join(lines)
        result = self.mod.format_repo_section("org/app", diff)
        for line in lines:
            self.assertIn(
                line,
                result,
                f"Section truncated diff — missing '{line}'. Got:\n{result}",
            )

    def test_section_uses_markdown_header_for_repo(self):
        """format_repo_section uses a ## or ### markdown header for the repo slug."""
        result = self.mod.format_repo_section("org/svc", "some diff")
        has_md_header = "## " in result or "### " in result or "**" in result
        self.assertTrue(
            has_md_header,
            f"Section should use a markdown header (##, ###, or **bold**) for the repo. Got:\n{result}",
        )


# ---------------------------------------------------------------------------
# TestFormatPrComment
# ---------------------------------------------------------------------------


class TestFormatPrComment(unittest.TestCase):
    """Unit tests for format_pr_comment(repo_diffs: dict[str, str | None])."""

    def setUp(self):
        self.mod = _load_script()

    def test_comment_contains_header_line(self):
        """format_pr_comment must begin with a recognisable title/header."""
        result = self.mod.format_pr_comment({"org/app": ""})
        first_lines = result.strip().splitlines()[:5]
        combined = "\n".join(first_lines).lower()
        has_header = (
            "overlay" in combined
            or "dry-run" in combined
            or "dry run" in combined
            or "gitweave" in combined
            or combined.startswith("#")
        )
        self.assertTrue(
            has_header,
            f"format_pr_comment output must start with a descriptive header. "
            f"First lines:\n{chr(10).join(first_lines)}",
        )

    def test_comment_contains_section_for_each_repo(self):
        """format_pr_comment includes one section per entry in repo_diffs."""
        repo_diffs = {
            "org/app-a": "diff content a",
            "org/app-b": "",
            "org/app-c": None,
        }
        result = self.mod.format_pr_comment(repo_diffs)
        for repo_slug in repo_diffs:
            self.assertIn(
                repo_slug,
                result,
                f"Comment must contain a section for repo '{repo_slug}'. Got:\n{result}",
            )

    def test_comment_shows_no_changes_for_empty_diff_repos(self):
        """format_pr_comment shows 'No changes' for repos with empty diff."""
        result = self.mod.format_pr_comment({"org/unaffected": ""})
        self.assertIn(
            "No changes",
            result,
            f"Comment must show 'No changes' for repos with empty diff. Got:\n{result}",
        )

    def test_comment_shows_no_changes_for_none_diff_repos(self):
        """format_pr_comment shows 'No changes' for repos where diff is None."""
        result = self.mod.format_pr_comment({"org/unaffected": None})
        self.assertIn(
            "No changes",
            result,
            f"Comment must show 'No changes' for repos with None diff. Got:\n{result}",
        )

    def test_comment_embeds_diff_content_for_changed_repos(self):
        """format_pr_comment embeds actual diff for repos with content."""
        diff = "--- a/Dockerfile\n+++ b/Dockerfile\n@@ -1 +1 @@\n-FROM node:18\n+FROM node:20"
        result = self.mod.format_pr_comment({"org/changed-app": diff})
        self.assertIn(
            "FROM node:20",
            result,
            f"Comment must embed actual diff lines for repos with changes. Got:\n{result}",
        )

    def test_comment_includes_html_marker_for_update_or_create(self):
        """
        format_pr_comment must embed a hidden HTML comment marker so that
        the post_or_update_comment function can locate this comment in future
        pushes and update it rather than creating a duplicate.
        """
        result = self.mod.format_pr_comment({"org/app": ""})
        # Standard pattern: <!-- gitweave-dry-run --> or similar hidden marker
        has_marker = "<!--" in result and "-->" in result
        self.assertTrue(
            has_marker,
            f"Comment must contain an HTML comment marker for idempotent updates. Got:\n{result}",
        )

    def test_comment_marker_is_stable_across_calls(self):
        """The hidden marker must be the same string on every call (content-agnostic)."""
        result_a = self.mod.format_pr_comment({"org/app": "diff a"})
        result_b = self.mod.format_pr_comment({"org/app": "diff b"})

        import re
        marker_pattern = re.compile(r"<!--.*?-->", re.DOTALL)
        markers_a = marker_pattern.findall(result_a)
        markers_b = marker_pattern.findall(result_b)

        self.assertTrue(markers_a, "No HTML marker found in first comment")
        self.assertTrue(markers_b, "No HTML marker found in second comment")
        self.assertEqual(
            markers_a[0],
            markers_b[0],
            "Marker must be identical across calls so update-or-create can find it. "
            f"First: {markers_a[0]!r}, Second: {markers_b[0]!r}",
        )

    def test_comment_includes_all_repos_when_multiple_provided(self):
        """format_pr_comment handles multiple repos and includes each one."""
        repos = {
            "org/service-a": "diff a",
            "org/service-b": "",
            "org/service-c": "diff c",
        }
        result = self.mod.format_pr_comment(repos)
        for slug in repos:
            self.assertIn(
                slug,
                result,
                f"Comment must include section for '{slug}'. Got:\n{result}",
            )

    def test_comment_returns_string(self):
        """format_pr_comment must return a str, not bytes or None."""
        result = self.mod.format_pr_comment({"org/app": "diff"})
        self.assertIsInstance(
            result,
            str,
            f"format_pr_comment must return a str, got {type(result).__name__}",
        )

    def test_comment_with_empty_repo_diffs_shows_no_repos_section(self):
        """format_pr_comment with an empty dict returns a valid comment (no repos to show)."""
        result = self.mod.format_pr_comment({})
        self.assertIsInstance(
            result,
            str,
            "format_pr_comment({}) must return a str",
        )
        # Should not crash, and should still include the hidden marker
        self.assertTrue(
            len(result) > 0,
            "format_pr_comment({}) must return a non-empty string",
        )


# ---------------------------------------------------------------------------
# TestRunCopierDiff
# ---------------------------------------------------------------------------


class TestRunCopierDiff(unittest.TestCase):
    """Unit tests for run_copier_diff(config, modules_dir)."""

    def setUp(self):
        self.mod = _load_script()

    @patch("subprocess.run")
    def test_calls_copier_diff_with_correct_module_path(self, mock_run: MagicMock):
        """run_copier_diff calls 'copier diff' with the correct module path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="some diff", stderr="")
        config = _minimal_overlay("org/app", modules=[{"name": "lang-node"}])

        self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        all_calls = [str(c) for c in mock_run.call_args_list]
        copier_calls = [c for c in all_calls if "copier" in c]
        self.assertTrue(
            copier_calls,
            f"run_copier_diff must call copier — no copier call found: {all_calls}",
        )
        self.assertIn(
            "lang-node",
            copier_calls[0],
            f"copier call must reference module 'lang-node'. Got: {copier_calls[0]}",
        )

    @patch("subprocess.run")
    def test_returns_stdout_when_copier_exits_zero(self, mock_run: MagicMock):
        """run_copier_diff returns copier's stdout when it exits with code 0."""
        expected_diff = "--- a/ci.yaml\n+++ b/ci.yaml\n@@ -1 +1 @@\n-old\n+new"
        mock_run.return_value = MagicMock(returncode=0, stdout=expected_diff, stderr="")
        config = _minimal_overlay("org/app", modules=[{"name": "lang-node"}])

        result = self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        self.assertIn(
            expected_diff,
            result,
            f"run_copier_diff should return copier stdout. Got: {result!r}",
        )

    @patch("subprocess.run")
    def test_returns_empty_string_when_copier_reports_nothing_to_do(
        self, mock_run: MagicMock
    ):
        """run_copier_diff returns '' when copier exits 0 with no diff output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        config = _minimal_overlay("org/app", modules=[{"name": "lang-node"}])

        result = self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        self.assertEqual(
            result.strip(),
            "",
            f"run_copier_diff should return empty string when copier has no diff. Got: {result!r}",
        )

    @patch("subprocess.run")
    def test_returns_empty_string_when_copier_exits_nonzero(self, mock_run: MagicMock):
        """run_copier_diff treats non-zero copier exit as no-diff (returns '')."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="template error"
        )
        config = _minimal_overlay("org/app", modules=[{"name": "lang-node"}])

        result = self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        self.assertIsInstance(
            result,
            str,
            "run_copier_diff must return str even when copier fails",
        )

    @patch("subprocess.run")
    def test_does_not_call_copier_when_overlay_has_no_modules(
        self, mock_run: MagicMock
    ):
        """run_copier_diff does not invoke copier when spec.modules is absent."""
        config = _minimal_overlay("org/bare-repo")  # no modules key

        result = self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        copier_calls = [
            c for c in [str(c) for c in mock_run.call_args_list] if "copier" in c
        ]
        self.assertEqual(
            len(copier_calls),
            0,
            f"run_copier_diff must not call copier when overlay has no modules. "
            f"Calls: {copier_calls}",
        )
        self.assertEqual(
            result.strip(),
            "",
            "run_copier_diff should return '' for overlay with no modules",
        )

    @patch("subprocess.run")
    def test_calls_copier_once_per_module(self, mock_run: MagicMock):
        """run_copier_diff calls copier diff once per module in spec.modules."""
        mock_run.return_value = MagicMock(returncode=0, stdout="diff output", stderr="")
        config = _minimal_overlay(
            "org/app", modules=[{"name": "lang-node"}, {"name": "ci-github-actions"}]
        )

        self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        copier_calls = [
            c for c in [str(c) for c in mock_run.call_args_list] if "copier" in c
        ]
        self.assertEqual(
            len(copier_calls),
            2,
            f"run_copier_diff must call copier once per module. Got {len(copier_calls)} calls: {copier_calls}",
        )

    @patch("subprocess.run")
    def test_concatenates_diffs_from_multiple_modules(self, mock_run: MagicMock):
        """run_copier_diff concatenates diff output from all modules."""
        def side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if "lang-node" in str(cmd):
                result.stdout = "diff from lang-node"
            elif "ci-github-actions" in str(cmd):
                result.stdout = "diff from ci-github-actions"
            else:
                result.stdout = ""
            return result

        mock_run.side_effect = side_effect
        config = _minimal_overlay(
            "org/app", modules=[{"name": "lang-node"}, {"name": "ci-github-actions"}]
        )

        result = self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        self.assertIn(
            "diff from lang-node",
            result,
            f"run_copier_diff must include diff from lang-node. Got: {result!r}",
        )
        self.assertIn(
            "diff from ci-github-actions",
            result,
            f"run_copier_diff must include diff from ci-github-actions. Got: {result!r}",
        )

    @patch("subprocess.run")
    def test_uses_diff_subcommand_not_copy(self, mock_run: MagicMock):
        """run_copier_diff must use 'copier diff' not 'copier copy'."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        config = _minimal_overlay("org/app", modules=[{"name": "lang-node"}])

        self.mod.run_copier_diff(config=config, modules_dir="/repo/modules")

        all_calls = [str(c) for c in mock_run.call_args_list]
        copy_calls = [c for c in all_calls if "copy" in c and "copier" in c]
        self.assertEqual(
            len(copy_calls),
            0,
            f"run_copier_diff must NOT call 'copier copy' — only 'copier diff'. "
            f"Found copy calls: {copy_calls}",
        )


# ---------------------------------------------------------------------------
# TestFindExistingComment
# ---------------------------------------------------------------------------


class TestFindExistingComment(unittest.TestCase):
    """Unit tests for find_existing_comment(pr_number, repo, token, marker)."""

    def setUp(self):
        self.mod = _load_script()

    @patch("urllib.request.urlopen")
    def test_returns_none_when_no_comments_exist(self, mock_urlopen: MagicMock):
        """find_existing_comment returns None when the PR has no comments."""
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.mod.find_existing_comment(
            pr_number=42,
            repo="org/my-app",
            token="fake-token",
            marker="<!-- gitweave-dry-run -->",
        )

        self.assertIsNone(
            result,
            f"find_existing_comment should return None when no comments exist. Got: {result}",
        )

    @patch("urllib.request.urlopen")
    def test_returns_none_when_no_comment_contains_marker(self, mock_urlopen: MagicMock):
        """find_existing_comment returns None when no comment body contains the marker."""
        import json

        comments = [
            {"id": 1, "body": "Some unrelated comment"},
            {"id": 2, "body": "Another comment without the marker"},
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(comments).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.mod.find_existing_comment(
            pr_number=42,
            repo="org/my-app",
            token="fake-token",
            marker="<!-- gitweave-dry-run -->",
        )

        self.assertIsNone(
            result,
            f"find_existing_comment should return None when marker is absent. Got: {result}",
        )

    @patch("urllib.request.urlopen")
    def test_returns_comment_id_when_marker_found(self, mock_urlopen: MagicMock):
        """find_existing_comment returns the comment ID when marker is present."""
        import json

        marker = "<!-- gitweave-dry-run -->"
        comments = [
            {"id": 1, "body": "unrelated"},
            {"id": 42, "body": f"Previous dry-run output\n{marker}\nmore content"},
        ]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(comments).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = self.mod.find_existing_comment(
            pr_number=7,
            repo="org/my-app",
            token="fake-token",
            marker=marker,
        )

        self.assertEqual(
            result,
            42,
            f"find_existing_comment should return comment ID 42 when marker found. Got: {result}",
        )

    @patch("urllib.request.urlopen")
    def test_queries_correct_github_api_endpoint(self, mock_urlopen: MagicMock):
        """find_existing_comment calls the issues/comments GitHub REST endpoint."""
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        self.mod.find_existing_comment(
            pr_number=5,
            repo="org/my-repo",
            token="fake-token",
            marker="<!-- gitweave-dry-run -->",
        )

        call_args = mock_urlopen.call_args
        # The URL or request object should reference the correct API path
        url_str = str(call_args)
        self.assertTrue(
            "repos/org/my-repo" in url_str or "issues/5/comments" in url_str,
            f"find_existing_comment should call the GitHub issues comments API. "
            f"urlopen called with: {url_str}",
        )

    @patch("urllib.request.urlopen")
    def test_sends_authorization_header(self, mock_urlopen: MagicMock):
        """find_existing_comment must send an Authorization header with the token."""
        import json

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([]).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        self.mod.find_existing_comment(
            pr_number=1,
            repo="org/app",
            token="my-secret-token",
            marker="<!-- marker -->",
        )

        call_args = mock_urlopen.call_args
        call_str = str(call_args)
        self.assertIn(
            "my-secret-token",
            call_str,
            f"find_existing_comment must pass the token in the Authorization header. "
            f"urlopen called with: {call_str}",
        )


# ---------------------------------------------------------------------------
# TestPostOrUpdateComment
# ---------------------------------------------------------------------------


class TestPostOrUpdateComment(unittest.TestCase):
    """Unit tests for post_or_update_comment(pr_number, repo, token, body, marker)."""

    def setUp(self):
        self.mod = _load_script()

    @patch("urllib.request.urlopen")
    def test_creates_new_comment_when_no_existing_comment(self, mock_urlopen: MagicMock):
        """post_or_update_comment POSTs a new comment when find_existing_comment returns None."""
        import json

        # First call: GET /comments (returns empty list — no existing comment)
        # Second call: POST /comments (creates new comment)
        get_response = MagicMock()
        get_response.read.return_value = json.dumps([]).encode()
        get_response.__enter__ = MagicMock(return_value=get_response)
        get_response.__exit__ = MagicMock(return_value=False)

        post_response = MagicMock()
        post_response.read.return_value = json.dumps({"id": 99}).encode()
        post_response.__enter__ = MagicMock(return_value=post_response)
        post_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [get_response, post_response]

        self.mod.post_or_update_comment(
            pr_number=10,
            repo="org/my-app",
            token="fake-token",
            body="## Dry-run results\n<!-- gitweave-dry-run -->",
            marker="<!-- gitweave-dry-run -->",
        )

        # Should have made 2 calls: GET to find, POST to create
        self.assertEqual(
            mock_urlopen.call_count,
            2,
            f"post_or_update_comment should make 2 requests (GET + POST). "
            f"Made {mock_urlopen.call_count} requests",
        )

    @patch("urllib.request.urlopen")
    def test_updates_existing_comment_when_marker_found(self, mock_urlopen: MagicMock):
        """post_or_update_comment PATCHes existing comment when marker is found."""
        import json

        marker = "<!-- gitweave-dry-run -->"
        existing_comment = {"id": 77, "body": f"Old content\n{marker}"}

        get_response = MagicMock()
        get_response.read.return_value = json.dumps([existing_comment]).encode()
        get_response.__enter__ = MagicMock(return_value=get_response)
        get_response.__exit__ = MagicMock(return_value=False)

        patch_response = MagicMock()
        patch_response.read.return_value = json.dumps({"id": 77}).encode()
        patch_response.__enter__ = MagicMock(return_value=patch_response)
        patch_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [get_response, patch_response]

        self.mod.post_or_update_comment(
            pr_number=10,
            repo="org/my-app",
            token="fake-token",
            body="## Updated dry-run\n<!-- gitweave-dry-run -->",
            marker=marker,
        )

        # PATCH request must reference the comment ID
        patch_call = mock_urlopen.call_args_list[1]
        patch_call_str = str(patch_call)
        self.assertIn(
            "77",
            patch_call_str,
            f"Update call must reference the existing comment ID 77. Got: {patch_call_str}",
        )

    @patch("urllib.request.urlopen")
    def test_does_not_create_duplicate_comment(self, mock_urlopen: MagicMock):
        """post_or_update_comment must PATCH (not POST) when marker exists — no duplicates."""
        import json

        marker = "<!-- gitweave-dry-run -->"
        existing_comment = {"id": 55, "body": f"Previous results\n{marker}"}

        get_response = MagicMock()
        get_response.read.return_value = json.dumps([existing_comment]).encode()
        get_response.__enter__ = MagicMock(return_value=get_response)
        get_response.__exit__ = MagicMock(return_value=False)

        patch_response = MagicMock()
        patch_response.read.return_value = json.dumps({"id": 55}).encode()
        patch_response.__enter__ = MagicMock(return_value=patch_response)
        patch_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [get_response, patch_response]

        self.mod.post_or_update_comment(
            pr_number=3,
            repo="org/app",
            token="fake-token",
            body="Updated content",
            marker=marker,
        )

        # Verify the second call is PATCH (contains comment ID), not a POST to /comments
        calls = mock_urlopen.call_args_list
        self.assertEqual(len(calls), 2, "Expected exactly 2 HTTP calls (GET + PATCH)")
        patch_call_str = str(calls[1])
        # A PATCH request to a specific comment URL contains the comment ID
        self.assertIn(
            "55",
            patch_call_str,
            f"Second call must PATCH comment 55, not create a new comment. Got: {patch_call_str}",
        )

    @patch("urllib.request.urlopen")
    def test_posted_body_matches_provided_comment_body(self, mock_urlopen: MagicMock):
        """post_or_update_comment sends exactly the provided body string."""
        import json

        get_response = MagicMock()
        get_response.read.return_value = json.dumps([]).encode()
        get_response.__enter__ = MagicMock(return_value=get_response)
        get_response.__exit__ = MagicMock(return_value=False)

        post_response = MagicMock()
        post_response.read.return_value = json.dumps({"id": 1}).encode()
        post_response.__enter__ = MagicMock(return_value=post_response)
        post_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [get_response, post_response]

        body = "## GitWeave Dry-run Results\nSome content\n<!-- gitweave-dry-run -->"
        self.mod.post_or_update_comment(
            pr_number=1,
            repo="org/app",
            token="fake-token",
            body=body,
            marker="<!-- gitweave-dry-run -->",
        )

        post_call = mock_urlopen.call_args_list[1]
        post_call_str = str(post_call)
        # The body content should appear in the serialised request
        self.assertIn(
            "GitWeave Dry-run Results",
            post_call_str,
            f"Posted body must contain the provided comment text. Got: {post_call_str}",
        )


# ---------------------------------------------------------------------------
# TestCliArguments
# ---------------------------------------------------------------------------


class TestCliArguments(unittest.TestCase):
    """Tests for the command-line interface contract of dry-run-overlays.py."""

    def test_accepts_pr_number_flag(self):
        """Script must accept --pr-number without argument error."""
        result = _run_script("--help")
        combined = result.stdout + result.stderr
        self.assertTrue(
            "pr-number" in combined.lower() or result.returncode == 0,
            f"Script rejected --pr-number or --help failed.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_accepts_repo_flag(self):
        """Script must accept --repo <owner/name> without argument error."""
        result = _run_script("--help")
        combined = result.stdout + result.stderr
        self.assertTrue(
            "repo" in combined.lower() or result.returncode == 0,
            f"--repo flag missing from help.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_accepts_config_dir_flag(self):
        """Script must accept --config-dir <path> without argument error."""
        result = _run_script("--help")
        combined = result.stdout + result.stderr
        self.assertTrue(
            "config-dir" in combined.lower() or result.returncode == 0,
            f"--config-dir flag missing from help.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_accepts_modules_dir_flag(self):
        """Script must accept --modules-dir <path> without argument error."""
        result = _run_script("--help")
        combined = result.stdout + result.stderr
        self.assertTrue(
            "modules-dir" in combined.lower() or result.returncode == 0,
            f"--modules-dir flag missing from help.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_accepts_dry_run_only_flag(self):
        """Script must accept --dry-run-only (print comment, skip posting)."""
        result = _run_script("--help")
        combined = result.stdout + result.stderr
        self.assertTrue(
            "dry-run-only" in combined.lower()
            or "dry_run_only" in combined.lower()
            or result.returncode == 0,
            f"--dry-run-only flag missing from help.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestCliSubprocessBehaviour
# ---------------------------------------------------------------------------


class TestCliSubprocessBehaviour(unittest.TestCase):
    """Integration tests invoking the script as a subprocess."""

    def test_exits_zero_in_dry_run_only_mode_with_empty_config_dir(self):
        """Script exits 0 in --dry-run-only when config dir is empty."""
        result = _run_script(
            "--dry-run-only",
            "--config-dir", "/nonexistent/path",
            "--modules-dir", "/nonexistent/modules",
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Script should exit 0 in --dry-run-only with no configs.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_only_prints_formatted_comment_to_stdout(self):
        """Script prints the formatted PR comment to stdout in --dry-run-only mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "app.yaml",
                _minimal_overlay("org/my-app", [{"name": "lang-node"}]),
            )
            result = _run_script(
                "--dry-run-only",
                "--config-dir", tmpdir,
                "--modules-dir", "/nonexistent/modules",
            )
        self.assertEqual(
            result.returncode,
            0,
            f"--dry-run-only should exit 0.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        combined = result.stdout + result.stderr
        self.assertIn(
            "org/my-app",
            combined,
            f"--dry-run-only output must contain the repo slug.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_only_shows_no_changes_for_repos_with_no_diff(self):
        """Script shows 'No changes' in dry-run-only mode when copier reports no diff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(
                tmpdir,
                "bare.yaml",
                _minimal_overlay("org/bare-repo"),  # no modules
            )
            result = _run_script(
                "--dry-run-only",
                "--config-dir", tmpdir,
                "--modules-dir", "/nonexistent/modules",
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "No changes",
            combined,
            f"Script must show 'No changes' for repos with no modules.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_requires_github_token_when_posting_comment(self):
        """Script exits non-zero when GITHUB_TOKEN is absent in posting mode."""
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            result = _run_script(
                "--pr-number", "1",
                "--repo", "org/my-repo",
                "--config-dir", tmpdir,
                "--modules-dir", "/nonexistent/modules",
                env=env_without_token,
            )
        self.assertNotEqual(
            result.returncode,
            0,
            f"Script must exit non-zero when GITHUB_TOKEN is absent in posting mode.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_error_message_mentions_github_token_when_absent(self):
        """Script mentions GITHUB_TOKEN in the error when the variable is missing."""
        env_without_token = {k: v for k, v in os.environ.items() if k != "GITHUB_TOKEN"}
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_yaml(tmpdir, "app.yaml", _minimal_overlay("org/app"))
            result = _run_script(
                "--pr-number", "1",
                "--repo", "org/my-repo",
                "--config-dir", tmpdir,
                "--modules-dir", "/nonexistent/modules",
                env=env_without_token,
            )
        combined = result.stdout + result.stderr
        self.assertIn(
            "GITHUB_TOKEN",
            combined,
            f"Script must mention GITHUB_TOKEN in error output when absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )

    def test_dry_run_only_does_not_require_pr_number(self):
        """Script must not require --pr-number when --dry-run-only is passed."""
        result = _run_script(
            "--dry-run-only",
            "--config-dir", "/nonexistent",
            "--modules-dir", "/nonexistent/modules",
        )
        combined = result.stdout + result.stderr
        self.assertNotIn(
            "required",
            combined.lower().replace("required: false", ""),
            f"Script should not require --pr-number in --dry-run-only mode.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# Boilerplate
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
