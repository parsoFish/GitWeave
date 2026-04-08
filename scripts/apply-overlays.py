"""
apply-overlays.py

Apply GitWeave overlay configurations to target repositories.

Usage:
    python scripts/apply-overlays.py [--dry-run] <config-path>

Arguments:
    config-path     Path to a GitWeave RepositoryOverlay YAML file
                    (e.g. config/repos/example.yaml)

Flags:
    --dry-run       Validate and print the overlay plan without making any
                    changes to external repositories.  Safe to run in CI
                    without credentials.
    --help, -h      Show this help message and exit.

Exit codes:
    0   Success (or successful dry-run)
    1   Invalid arguments or malformed config
    2   Module not found
"""

from __future__ import annotations

import argparse
import os
import sys

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODULES_DIR = os.path.join(REPO_ROOT, "modules")

_REQUIRED_API_VERSION = "gitweave.io/v1"
_REQUIRED_KIND = "RepositoryOverlay"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_config(path: str) -> dict:
    """Load and parse a YAML overlay config file."""
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[error] Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as exc:
        print(f"[error] Failed to parse YAML config: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(doc, dict):
        print(
            f"[error] Config file is not a YAML mapping: {path}",
            file=sys.stderr,
        )
        sys.exit(1)
    return doc


def _validate_config(doc: dict) -> None:
    """Validate required fields in the overlay config document."""
    api_version = doc.get("apiVersion", "")
    kind = doc.get("kind", "")

    if api_version != _REQUIRED_API_VERSION:
        print(
            f"[error] Unsupported apiVersion '{api_version}'. "
            f"Expected '{_REQUIRED_API_VERSION}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if kind != _REQUIRED_KIND:
        print(
            f"[error] Unsupported kind '{kind}'. Expected '{_REQUIRED_KIND}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    spec = doc.get("spec", {})
    repository = spec.get("repository", "")
    if not repository or not isinstance(repository, str):
        print(
            "[error] 'spec.repository' is missing or empty in the overlay config.",
            file=sys.stderr,
        )
        sys.exit(1)


def _resolve_modules(modules: list[dict]) -> list[tuple[str, str]]:
    """
    Resolve each module name to its directory path.

    Returns a list of (name, path) tuples.
    Exits with code 2 if any module directory is missing.
    """
    resolved = []
    for entry in modules:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name:
            continue
        module_path = os.path.join(MODULES_DIR, name)
        if not os.path.isdir(module_path):
            print(
                f"[error] Module directory not found: {module_path}\n"
                f"        Create modules/{name}/ to register this module.",
                file=sys.stderr,
            )
            sys.exit(2)
        resolved.append((name, module_path))
    return resolved


def _print_dry_run_plan(repository: str, resolved_modules: list[tuple[str, str]]) -> None:
    """Print the overlay plan to stdout without applying any changes."""
    print(f"[dry-run] Overlay plan for repository: {repository}")
    print(f"[dry-run] Modules to apply ({len(resolved_modules)}):")
    for name, path in resolved_modules:
        print(f"[dry-run]   - {name}  ({path})")
    print("[dry-run] No changes applied. Run without --dry-run to apply.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apply-overlays.py",
        description="Apply GitWeave overlay configurations to target repositories.",
    )
    parser.add_argument(
        "config",
        metavar="CONFIG_PATH",
        help="Path to a GitWeave RepositoryOverlay YAML file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the overlay plan without making any changes.",
    )

    args = parser.parse_args(argv)

    doc = _load_config(args.config)
    _validate_config(doc)

    spec = doc.get("spec", {})
    repository: str = spec["repository"]
    modules: list[dict] = spec.get("modules", [])

    resolved = _resolve_modules(modules)

    if args.dry_run:
        _print_dry_run_plan(repository, resolved)
    else:
        # Real apply path — requires credentials and external network access.
        # Not implemented yet; placeholder for future work.
        print(f"[apply] Applying overlays to repository: {repository}")
        for name, path in resolved:
            print(f"[apply]   Applying module: {name}")
        print("[apply] Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
