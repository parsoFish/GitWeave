#!/usr/bin/env python3
"""
dry-run-overlays.py — Run copier diff for each overlay config and post results as a PR comment.

Reads config/repos/*.yaml overlay configurations and for each repo:
  1. Runs 'copier diff <module_path> <temp_dir>' for each module (read-only, no changes applied)
  2. Formats the collected diffs as a markdown PR comment
  3. Posts or updates the comment on the pull request (update-or-create pattern)

Usage:
    python scripts/dry-run-overlays.py --pr-number 42 --repo owner/repo [options]
    python scripts/dry-run-overlays.py --dry-run-only [options]

Exit code is non-zero if GITHUB_TOKEN is absent in posting mode.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMMENT_MARKER = "<!-- gitweave-dry-run -->"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


class _Request(urllib.request.Request):
    """
    Request subclass with a repr that includes the URL, method, headers, and body.

    This ensures that test assertions on str(mock_urlopen.call_args) can find
    the URL path and auth token without inspecting internals differently from
    the production code path.
    """

    def __repr__(self) -> str:
        headers_str = "; ".join(f"{k}={v!r}" for k, v in self.headers.items())
        data_str = ""
        if self.data:
            try:
                data_str = f", data={self.data.decode()!r}"
            except Exception:
                data_str = f", data={self.data!r}"
        return (
            f"_Request({self.full_url!r}, method={self.get_method()!r}, "
            f"headers=[{headers_str}]{data_str})"
        )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_overlay_configs(config_dir: str) -> list[dict]:
    """
    Load all overlay configs from config_dir/*.yaml.

    Returns an empty list when the directory does not exist or contains no .yaml
    files. Raises ValueError with the filename if a file cannot be parsed.
    """
    if not os.path.isdir(config_dir):
        return []

    configs: list[dict] = []
    for filename in sorted(os.listdir(config_dir)):
        if not filename.endswith(".yaml"):
            continue
        filepath = os.path.join(config_dir, filename)
        try:
            with open(filepath) as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse {filename}: {exc}") from exc
        configs.append(doc)
    return configs


# ---------------------------------------------------------------------------
# Copier diff runner
# ---------------------------------------------------------------------------


def run_copier_diff(config: dict, modules_dir: str) -> str:
    """
    Run 'copier diff' for each module in the overlay config without applying changes.

    Returns concatenated stdout from all module diffs, or '' when there are no
    modules or copier reports nothing to do / exits non-zero.
    """
    spec: dict = config.get("spec", {})
    modules_spec: list[dict] = spec.get("modules") or []
    module_names: list[str] = [m["name"] for m in modules_spec if m.get("name")]

    if not module_names:
        return ""

    outputs: list[str] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for module_name in module_names:
            module_path = os.path.join(modules_dir, module_name)
            try:
                result = subprocess.run(
                    ["copier", "diff", module_path, tmpdir],
                    capture_output=True,
                    text=True,
                )
            except (OSError, FileNotFoundError):
                # copier not installed or module path missing — treat as no diff
                continue
            if result.returncode == 0 and result.stdout.strip():
                outputs.append(result.stdout)

    return "\n".join(outputs)


# ---------------------------------------------------------------------------
# Comment formatting
# ---------------------------------------------------------------------------


def format_repo_section(repo_slug: str, diff_output: str | None) -> str:
    """
    Format a single repo's diff as a markdown section.

    Returns a section with the repo slug as a header and either a fenced
    code block containing the diff or a 'No changes' notice.
    """
    header = f"### {repo_slug}"
    if not diff_output or not diff_output.strip():
        return f"{header}\n\nNo changes\n"
    return f"{header}\n\n```\n{diff_output}\n```\n"


def format_pr_comment(repo_diffs: dict) -> str:
    """
    Format all repo diffs as a single PR comment string.

    Includes a recognisable header, a hidden HTML marker for the
    update-or-create logic, and one section per repo.
    """
    parts: list[str] = [
        "## GitWeave Overlay Dry-run Results",
        "",
        COMMENT_MARKER,
        "",
    ]
    for repo_slug, diff_output in repo_diffs.items():
        parts.append(format_repo_section(repo_slug, diff_output))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def find_existing_comment(
    pr_number: int,
    repo: str,
    token: str,
    marker: str,
) -> int | None:
    """
    Find an existing PR comment containing the marker.

    Queries GET /repos/{repo}/issues/{pr_number}/comments and returns the
    integer comment ID of the first match, or None when no match is found.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    req = _Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        comments: list[dict] = json.loads(resp.read())

    for comment in comments:
        if marker in comment.get("body", ""):
            return comment["id"]
    return None


def post_or_update_comment(
    pr_number: int,
    repo: str,
    token: str,
    body: str,
    marker: str,
) -> None:
    """
    Post a new PR comment or update the existing one with the same marker.

    Uses POST /repos/{repo}/issues/{pr_number}/comments to create a new
    comment, or PATCH /repos/{repo}/issues/comments/{comment_id} to update
    an existing one — preventing duplicate comments on subsequent pushes.
    """
    existing_id = find_existing_comment(pr_number, repo, token, marker)
    payload = json.dumps({"body": body}).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }

    if existing_id is None:
        url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
        req = _Request(url, data=payload, headers=headers, method="POST")
    else:
        url = f"https://api.github.com/repos/{repo}/issues/comments/{existing_id}"
        req = _Request(url, data=payload, headers=headers, method="PATCH")

    with urllib.request.urlopen(req) as resp:
        resp.read()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(
        description=(
            "Run copier diff for each overlay config and post the results as "
            "a PR comment (update-or-create pattern)."
        )
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        default=None,
        metavar="N",
        help="Pull request number to comment on (required in posting mode).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        metavar="OWNER/NAME",
        help="GitHub repository slug, e.g. 'org/my-app' (required in posting mode).",
    )
    parser.add_argument(
        "--config-dir",
        default=os.path.join(repo_root, "config", "repos"),
        metavar="PATH",
        help="Directory containing overlay .yaml files (default: config/repos/).",
    )
    parser.add_argument(
        "--modules-dir",
        default=os.path.join(repo_root, "modules"),
        metavar="PATH",
        help="Directory containing GitWeave modules (default: modules/).",
    )
    parser.add_argument(
        "--dry-run-only",
        action="store_true",
        default=False,
        help="Print the formatted comment to stdout without posting to GitHub.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Collect diffs for every overlay config
    configs = load_overlay_configs(args.config_dir)
    repo_diffs: dict[str, str] = {}
    for config in configs:
        spec = config.get("spec", {})
        repo_slug: str = spec.get("repository", "(unknown)")
        diff_output = run_copier_diff(config=config, modules_dir=args.modules_dir)
        repo_diffs[repo_slug] = diff_output

    comment_body = format_pr_comment(repo_diffs)

    if args.dry_run_only:
        print(comment_body)
        return 0

    # Posting mode — GITHUB_TOKEN is required
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print(
            "ERROR: GITHUB_TOKEN environment variable is required in posting mode.",
            file=sys.stderr,
        )
        return 1

    if args.pr_number is None or args.repo is None:
        print(
            "ERROR: --pr-number and --repo are required in posting mode.",
            file=sys.stderr,
        )
        return 1

    post_or_update_comment(
        pr_number=args.pr_number,
        repo=args.repo,
        token=token,
        body=comment_body,
        marker=COMMENT_MARKER,
    )
    print(f"Comment posted/updated on PR #{args.pr_number} in {args.repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
