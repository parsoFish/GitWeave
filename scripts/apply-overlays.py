#!/usr/bin/env python3
"""
apply-overlays.py — Apply GitWeave Copier overlays to target repositories.

Reads config/repos/*.yaml overlay configurations and applies each one by:
  1. Cloning the target repository (authenticated via GITHUB_TOKEN)
  2. Running 'copier copy <module-path>' for each module in spec.modules
  3. Committing and pushing changes on a new branch
  4. Opening a PR via 'gh pr create'

Usage:
    python scripts/apply-overlays.py [--dry-run] [--config-dir PATH] [--modules-dir PATH]

Exit code is non-zero if any repository application fails.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import yaml


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_overlay_configs(config_dir: str) -> list[dict]:
    """
    Load all overlay configs from config_dir/*.yaml.

    Returns an empty list when the directory does not exist or contains no .yaml
    files.  Raises a ValueError with the filename if a .yaml file cannot be
    parsed.
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
# Overlay application
# ---------------------------------------------------------------------------


def apply_overlay(
    config: dict,
    modules_dir: str,
    github_token: str,
    dry_run: bool = False,
) -> dict:
    """
    Apply a single overlay configuration to its target repository.

    In dry-run mode no subprocess is invoked; the function returns a result
    describing what *would* happen.

    Returns a result dict with at minimum:
      - repo: str — the repository slug (e.g. "org/my-app")
      - dry_run: bool — True only in dry-run mode
      - success: bool — True when all operations succeeded (absent in dry-run)
      - error: str — present and non-empty when success is False
      - modules: list[str] — module names (present in dry-run)
    """
    repo_slug: str = config.get("spec", {}).get("repository", "")
    modules_spec: list[dict] = config.get("spec", {}).get("modules") or []
    module_names: list[str] = [m["name"] for m in modules_spec if m.get("name")]

    if dry_run:
        return {
            "repo": repo_slug,
            "dry_run": True,
            "modules": module_names,
        }

    clone_url = f"https://x-access-token:{github_token}@github.com/{repo_slug}.git"
    branch_name = "gitweave/apply-overlays"

    with tempfile.TemporaryDirectory() as workdir:
        # Clone
        clone_result = subprocess.run(
            ["git", "clone", clone_url, workdir],
            capture_output=True,
            text=True,
        )
        if clone_result.returncode != 0:
            return {
                "repo": repo_slug,
                "success": False,
                "error": clone_result.stderr or "git clone failed",
            }

        # Create branch
        subprocess.run(
            ["git", "-C", workdir, "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
        )

        # Apply each module via copier
        for module_name in module_names:
            module_path = os.path.join(modules_dir, module_name)
            copier_result = subprocess.run(
                ["copier", "copy", "--overwrite", "--defaults", module_path, workdir],
                capture_output=True,
                text=True,
            )
            if copier_result.returncode != 0:
                return {
                    "repo": repo_slug,
                    "success": False,
                    "error": copier_result.stderr or f"copier failed for module {module_name}",
                }

        # Commit
        subprocess.run(
            ["git", "-C", workdir, "add", "--all"],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                workdir,
                "commit",
                "-m",
                "chore: apply GitWeave overlays",
                "--allow-empty",
            ],
            capture_output=True,
            text=True,
        )

        # Push
        push_result = subprocess.run(
            ["git", "-C", workdir, "push", "origin", branch_name, "--force"],
            capture_output=True,
            text=True,
        )
        if push_result.returncode != 0:
            return {
                "repo": repo_slug,
                "success": False,
                "error": push_result.stderr or "git push failed",
            }

        # Open PR — inherits GITHUB_TOKEN from the current process environment,
        # which main() has already validated is present.
        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo_slug,
                "--head",
                branch_name,
                "--title",
                "chore: apply GitWeave overlays",
                "--body",
                "Automated overlay application via GitWeave.",
                "--fill",
            ],
            capture_output=True,
            text=True,
        )
        if pr_result.returncode != 0:
            return {
                "repo": repo_slug,
                "success": False,
                "error": pr_result.stderr or "gh pr create failed",
            }

    return {"repo": repo_slug, "success": True}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(
        description="Apply GitWeave Copier overlays to target repositories."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be applied without executing any changes.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    github_token = os.environ.get("GITHUB_TOKEN", "")

    if not args.dry_run and not github_token:
        print(
            "ERROR: GITHUB_TOKEN environment variable is required in apply mode.",
            file=sys.stderr,
        )
        return 1

    configs = load_overlay_configs(args.config_dir)

    results: list[dict] = []
    for config in configs:
        result = apply_overlay(
            config=config,
            modules_dir=args.modules_dir,
            github_token=github_token,
            dry_run=args.dry_run,
        )
        results.append(result)
        repo = result.get("repo", "(unknown)")
        if result.get("dry_run"):
            modules = result.get("modules", [])
            modules_str = ", ".join(modules) if modules else "(none)"
            print(f"[DRY-RUN] {repo}: would apply modules: {modules_str}")
        elif result.get("success"):
            print(f"[OK]      {repo}: PR opened successfully")
        else:
            print(f"[FAILED]  {repo}: {result.get('error', 'unknown error')}")

    # Summary
    if args.dry_run:
        print(f"\nSummary (dry-run): {len(results)} repo(s) would be processed.")
        return 0

    succeeded = sum(1 for r in results if r.get("success"))
    failed = len(results) - succeeded
    print(f"\nSummary: {succeeded} succeeded, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
