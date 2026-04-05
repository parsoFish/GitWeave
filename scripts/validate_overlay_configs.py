#!/usr/bin/env python3
"""
Validate overlay config files in a directory against schemas/overlay.schema.json.

Usage:
    python3 scripts/validate_overlay_configs.py [config_dir]

Exits 0 if all .yaml files pass schema validation, non-zero if any fail.
"""

import argparse
import json
import os
import sys

import yaml
import jsonschema
from jsonschema import validate, ValidationError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "overlay.schema.json")


def load_schema(schema_path: str) -> dict:
    with open(schema_path) as f:
        return json.load(f)


def validate_directory(config_dir: str, schema: dict) -> bool:
    """Validate all .yaml files in config_dir. Returns True if all pass."""
    if not os.path.isdir(config_dir):
        print(f"Validated 0 files (directory does not exist: {config_dir})")
        return True

    yaml_files = sorted(
        f for f in os.listdir(config_dir) if f.endswith(".yaml")
    )

    if not yaml_files:
        print(f"Validated 0 files")
        return True

    failures = []

    for filename in yaml_files:
        filepath = os.path.join(config_dir, filename)
        try:
            with open(filepath) as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            print(f"FAIL {filename}: YAML parse error — {exc}")
            failures.append(filename)
            continue

        try:
            validate(instance=doc, schema=schema)
            print(f"OK   {filename}")
        except ValidationError as exc:
            print(f"FAIL {filename}: {exc.message}")
            failures.append(filename)

    file_word = "file" if len(yaml_files) == 1 else "files"
    print(f"Validated {len(yaml_files)} {file_word}")

    if failures:
        print(f"{len(failures)} file(s) failed validation: {', '.join(failures)}")
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate overlay config files against schemas/overlay.schema.json"
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default=os.path.join(REPO_ROOT, "config", "repos"),
        help="Directory containing .yaml overlay config files (default: config/repos/)",
    )
    args = parser.parse_args()

    schema = load_schema(DEFAULT_SCHEMA_PATH)
    success = validate_directory(args.config_dir, schema)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
