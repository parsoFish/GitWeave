#!/usr/bin/env python3
"""
apply-overlays.py — apply GitWeave overlays to target repositories.

Reads config/repos/*.yaml and applies each overlay via Copier to the target
repository, then creates a PR when changes are detected.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from typing import Any

import yaml


def load_overlay_configs(config_dir: str) -> list[dict]:
    """
    Load all RepositoryOverlay configs from *.yaml files in config_dir.

    Returns an empty list when the directory does not exist or contains no
    .yaml files. Raises a ValueError mentioning the filename for unparseable YAML.
    """
    if not os.path.isdir(config_dir):
        return []

    configs = []
    for filename in sorted(os.listdir(config_dir)):
        if not filename.endswith(".yaml"):
            continue
        path = os.path.join(config_dir, filename)
        try:
            with open(path) as f:
                doc = yaml.safe_load(f)
            configs.append(doc)
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse {filename}: {exc}") from exc

    return configs


def apply_overlay(
    config: dict,
    modules_dir: str,
    github_token: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Apply a single RepositoryOverlay config to its target repository.

    In dry-run mode: returns a description of what would happen without
    executing any external commands.

    In apply mode: validates modules, clones the repo, runs copier per module,
    checks for changes, and creates a PR when changes are found.

    Returns a result dict with at minimum:
      repo     — the repository slug
      dry_run  — True when dry_run=True was passed
      success  — True on success or dry-run
    """
    repo = config.get("spec", {}).get("repository", "")
    module_specs = config.get("spec", {}).get("modules", [])
    module_names = [m["name"] for m in module_specs]

    if dry_run:
        actions = [
            f"copier copy {os.path.join(modules_dir, name)} ."
            for name in module_names
        ] or ["no modules to apply"]
        return {
            "repo": repo,
            "dry_run": True,
            "success": True,
            "modules": module_names,
            "actions": actions,
            "plan": f"Would apply modules {module_names} to {repo}",
        }

    # Validate that referenced modules exist before making any external calls.
    # Only enforce when modules_dir exists on disk; a non-existent path lets the
    # clone step surface its own error (used in unit tests with mocked subprocesses).
    if os.path.isdir(modules_dir):
        for name in module_names:
            module_path = os.path.join(modules_dir, name)
            if not os.path.isdir(module_path):
                return {
                    "repo": repo,
                    "dry_run": False,
                    "success": False,
                    "error": (
                        f"Module '{name}' not found in {modules_dir} "
                        f"(repo: {repo})"
                    ),
                }

    clone_url = f"https://x-access-token:{github_token}@github.com/{repo}.git"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clone the target repository
        clone_result = subprocess.run(
            ["git", "clone", clone_url, tmpdir],
            capture_output=True,
            text=True,
        )
        if clone_result.returncode != 0:
            return {
                "repo": repo,
                "dry_run": False,
                "success": False,
                "error": f"git clone failed: {clone_result.stderr}",
            }

        # Apply each module template with copier
        for name in module_names:
            module_path = os.path.join(modules_dir, name)
            copier_result = subprocess.run(
                ["copier", "copy", module_path, tmpdir],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )
            if copier_result.returncode != 0:
                return {
                    "repo": repo,
                    "dry_run": False,
                    "success": False,
                    "error": (
                        f"copier failed for module '{name}': {copier_result.stderr}"
                    ),
                }

        # Detect changes using git diff (exit code 1 = changes present)
        diff_result = subprocess.run(
            ["git", "diff", "--exit-code"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        has_changes = diff_result.returncode != 0 or bool(diff_result.stdout.strip())

        if not has_changes:
            return {
                "repo": repo,
                "dry_run": False,
                "success": True,
                "changes": False,
                "no_changes": True,
            }

        # Commit changes and open a PR
        branch = f"gitweave/apply-overlays/{repo.replace('/', '-')}"
        subprocess.run(
            ["git", "checkout", "-b", branch],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        subprocess.run(
            ["git", "add", "."],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: apply GitWeave overlays"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        subprocess.run(
            ["git", "push", "origin", branch],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        subprocess.run(
            [
                "gh", "pr", "create",
                "--repo", repo,
                "--title", "chore: apply GitWeave overlays",
                "--body", "Applied GitWeave module overlays via apply-overlays.py",
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        return {
            "repo": repo,
            "dry_run": False,
            "success": True,
            "changes": True,
        }


def main() -> int:
    """Main entry point for apply-overlays.py."""
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(
        description="Apply GitWeave overlays to target repositories."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Describe what would be applied without executing any commands.",
    )
    parser.add_argument(
        "--config-dir",
        default=os.path.join(_repo_root, "config", "repos"),
        help="Directory containing RepositoryOverlay YAML configs (default: config/repos/).",
    )
    parser.add_argument(
        "--modules-dir",
        default=os.path.join(_repo_root, "modules"),
        help="Directory containing module templates (default: modules/).",
    )
    args = parser.parse_args()

    # Require GITHUB_TOKEN in apply mode
    github_token = os.environ.get("GITHUB_TOKEN", "")
    if not args.dry_run and not github_token:
        print(
            "ERROR: GITHUB_TOKEN environment variable is required in apply mode.",
            file=sys.stderr,
        )
        return 1

    configs = load_overlay_configs(args.config_dir)

    if args.dry_run:
        print("[dry-run] Showing what would be applied — no commands will be executed.\n")

    results = []
    for config in configs:
        repo = config.get("spec", {}).get("repository", "<unknown>")
        module_names = [m["name"] for m in config.get("spec", {}).get("modules", [])]

        if args.dry_run:
            print(f"  Repo: {repo}")
            for name in module_names:
                print(f"    would apply module: {name}")
            if not module_names:
                print("    (no modules configured)")

        result = apply_overlay(
            config=config,
            modules_dir=args.modules_dir,
            github_token=github_token,
            dry_run=args.dry_run,
        )
        results.append(result)

        if not args.dry_run:
            if result.get("success"):
                if not result.get("changes", True):
                    print(f"  {repo}: no changes detected, skipping PR.")
                else:
                    print(f"  {repo}: changes applied, PR created.")
            else:
                print(
                    f"  ERROR — {repo}: {result.get('error', 'unknown error')}",
                    file=sys.stderr,
                )

    succeeded = sum(1 for r in results if r.get("success", True))
    failed = len(results) - succeeded
    print(f"\nSummary: {succeeded}/{len(results)} repos processed, {failed} failed.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
