#!/usr/bin/env python3
"""
CI guard: assert that every workflow in .github/workflows/ declares an explicit
permissions block, preventing the implicit GITHUB_TOKEN write-all default.

Usage:
    python scripts/check_workflow_permissions.py [workflows_dir]

Exits 0 when all workflows are compliant, non-zero otherwise.
"""

from __future__ import annotations

import os
import sys

import yaml


def _has_explicit_permissions(doc: dict) -> bool:
    """
    Return True when a workflow has explicit permissions at the top level OR
    on every individual job.  Either form prevents jobs from inheriting the
    write-all default.
    """
    if "permissions" in doc:
        return True
    jobs = doc.get("jobs") or {}
    if not jobs:
        return False
    return all("permissions" in job for job in jobs.values())


def check_directory(workflows_dir: str) -> list[str]:
    """
    Scan *workflows_dir* for YAML workflow files and return a list of
    non-compliant filenames.  An empty list means everything is compliant.
    """
    violations: list[str] = []
    try:
        entries = sorted(os.listdir(workflows_dir))
    except FileNotFoundError:
        print(f"ERROR: directory not found: {workflows_dir}", file=sys.stderr)
        sys.exit(2)

    yaml_files = [e for e in entries if e.endswith((".yaml", ".yml"))]
    for filename in yaml_files:
        path = os.path.join(workflows_dir, filename)
        with open(path) as f:
            try:
                doc = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                print(f"ERROR: could not parse {filename}: {exc}", file=sys.stderr)
                violations.append(filename)
                continue

        if not _has_explicit_permissions(doc):
            violations.append(filename)

    return violations


def main() -> None:
    workflows_dir = sys.argv[1] if len(sys.argv) > 1 else ".github/workflows"

    violations = check_directory(workflows_dir)

    if not violations:
        print(f"OK: all workflows in '{workflows_dir}' declare explicit permissions.")
        sys.exit(0)

    print(
        f"FAIL: the following workflow(s) are missing explicit permissions blocks "
        f"(they inherit the write-all default):",
        file=sys.stderr,
    )
    for name in violations:
        print(f"  - {name}", file=sys.stderr)
    print(
        "\nAdd a top-level 'permissions:' block or add 'permissions:' to every job.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
