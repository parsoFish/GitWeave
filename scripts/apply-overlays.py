#!/usr/bin/env python3
"""
apply-overlays.py — Apply GitWeave Copier overlays to target repositories.

Reads config/repos/*.yaml overlay configurations and applies each one by:
  1. Cloning the target repository (authenticated via GITHUB_TOKEN)
  2. Running 'copier copy <module-path>' for each module in spec.modules
  3. Committing and pushing changes on a new branch
  4. Opening a PR via 'gh pr create'

Usage:
    python scripts/apply-overlays.py [--dry-run] [--env NAME] [--config-dir PATH] [--modules-dir PATH]

Exit code is non-zero if any repository application fails.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
import tempfile

import yaml


# ---------------------------------------------------------------------------
# Variable merge helpers
# ---------------------------------------------------------------------------


def merge_variables(base: dict, env_override: dict) -> dict:
    """
    Merge environment-specific variable overrides over base variables.

    Returns a new dict where:
      - env_override values replace base values for shared keys (env wins)
      - base-only keys are preserved unchanged
      - env-only keys are added to the result
      - neither input dict is mutated
    """
    return {**base, **env_override}


def resolve_env_name(pattern: str, repo: str) -> str | None:
    """
    Resolve an environment name or glob pattern to a concrete name.

    For plain names (no glob characters), the pattern is returned as-is
    without any external calls.

    For patterns containing '*', '?', or '[', the gh CLI lists branches for
    the given repo and returns the first branch matching the glob pattern,
    or None if no branch matches.
    """
    if "*" not in pattern and "?" not in pattern and "[" not in pattern:
        return pattern

    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/branches", "--jq", ".[].name"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    branches = [b.strip() for b in result.stdout.splitlines() if b.strip()]
    for branch in branches:
        if fnmatch.fnmatch(branch, pattern):
            return branch
    return None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def filter_overlays_by_environment(configs: list[dict], env: str | None) -> list[dict]:
    """
    Return only overlays that declare spec.environments.<env>.

    When env is None or an empty string, returns all configs unchanged
    (backward-compatible behaviour — no filtering applied).

    The input list is not mutated; a new list is always returned.
    """
    if not env:
        return list(configs)
    return [
        config
        for config in configs
        if env in ((config.get("spec") or {}).get("environments") or {})
    ]


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


def _build_copier_data_flags(variables: dict) -> list[str]:
    """Return a flat list of --data KEY=VALUE flags for each entry in variables."""
    flags: list[str] = []
    for key, value in variables.items():
        flags.extend(["--data", f"{key}={value}"])
    return flags


def apply_overlay(
    config: dict,
    modules_dir: str,
    github_token: str,
    dry_run: bool = False,
    env: str | None = None,
) -> dict:
    """
    Apply a single overlay configuration to its target repository.

    When env is provided, spec.environments.<env>.variables are merged over
    spec.variables (environment values take precedence).  The resolved variables
    are forwarded to each copier invocation via --data KEY=VALUE flags.

    In dry-run mode no subprocess is invoked; the function returns a result
    describing what *would* happen.

    Returns a result dict with at minimum:
      - repo: str — the repository slug (e.g. "org/my-app")
      - dry_run: bool — True only in dry-run mode
      - success: bool — True when all operations succeeded (absent in dry-run)
      - error: str — present and non-empty when success is False
      - modules: list[str] — module names (present in dry-run)
      - merged_variables: dict — resolved variables after env merge (when variables exist)
    """
    spec: dict = config.get("spec", {})
    repo_slug: str = spec.get("repository", "")
    modules_spec: list[dict] = spec.get("modules") or []
    module_names: list[str] = [m["name"] for m in modules_spec if m.get("name")]

    # Resolve merged variables: base + optional env override
    base_variables: dict = spec.get("variables") or {}
    env_override: dict = {}
    if env:
        environments: dict = spec.get("environments") or {}
        env_config: dict = environments.get(env) or {}
        env_override = env_config.get("variables") or {}
    merged_vars: dict = merge_variables(base_variables, env_override)

    if dry_run:
        result: dict = {
            "repo": repo_slug,
            "dry_run": True,
            "modules": module_names,
        }
        if env:
            result["env"] = env
        if merged_vars:
            result["merged_variables"] = merged_vars
        return result

    clone_url = f"https://x-access-token:{github_token}@github.com/{repo_slug}.git"
    branch_name = "gitweave/apply-overlays"
    data_flags = _build_copier_data_flags(merged_vars)

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

        # Apply each module via copier, forwarding resolved variables as --data flags
        for module_name in module_names:
            module_path = os.path.join(modules_dir, module_name)
            copier_cmd = [
                "copier", "copy", "--overwrite", "--defaults",
                *data_flags,
                module_path, workdir,
            ]
            copier_result = subprocess.run(
                copier_cmd,
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
        "--env",
        default=None,
        metavar="NAME",
        help=(
            "Target environment name (e.g. staging, prod). "
            "When set, spec.environments.<NAME>.variables are merged over "
            "spec.variables before running copier. Supports glob patterns "
            "(e.g. 'feature/*') resolved via the gh API."
        ),
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
    configs = filter_overlays_by_environment(configs, args.env)

    if args.env:
        print(f"[INFO] Filtering overlays for environment: {args.env}", file=sys.stderr)

    results: list[dict] = []
    for config in configs:
        result = apply_overlay(
            config=config,
            modules_dir=args.modules_dir,
            github_token=github_token,
            dry_run=args.dry_run,
            env=args.env,
        )
        results.append(result)
        repo = result.get("repo", "(unknown)")
        if result.get("dry_run"):
            modules = result.get("modules", [])
            modules_str = ", ".join(modules) if modules else "(none)"
            env_label = f" [env={result['env']}]" if result.get("env") else ""
            print(f"[DRY-RUN]{env_label} {repo}: would apply modules: {modules_str}")
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
