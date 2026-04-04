#!/usr/bin/env python3
"""
Validate all config/repos/*.yaml files against schemas/overlay.schema.json.

Usage:
    python3 scripts/validate_overlay_configs.py [config/repos/]

The directory argument defaults to config/repos/ relative to the repo root.
Exits 0 when all files are valid (or the directory is empty/absent).
Exits 1 if any file fails validation, printing the file name and specific violation.
"""

import argparse
import json
import os
import sys

import yaml
import jsonschema
from jsonschema import validate, ValidationError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "overlay.schema.json")
DEFAULT_CONFIG_DIR = os.path.join(REPO_ROOT, "config", "repos")


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _validate_file(path: str, schema: dict) -> list[str]:
    """Return a list of error messages for the given YAML file, or [] if valid."""
    errors = []
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        errors.append(f"YAML parse error: {exc}")
        return errors

    validator = jsonschema.Draft7Validator(schema)
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        errors.append(error.message)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate overlay YAML files against schemas/overlay.schema.json"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=DEFAULT_CONFIG_DIR,
        help="Directory containing overlay YAML files (default: config/repos/)",
    )
    args = parser.parse_args()

    directory = args.directory

    if not os.path.isdir(directory):
        print(f"Validated 0 file(s) (directory does not exist: {directory})")
        return 0

    schema = _load_schema()

    yaml_files = sorted(
        entry.name
        for entry in os.scandir(directory)
        if entry.is_file() and entry.name.endswith(".yaml")
    )

    if not yaml_files:
        print(f"Validated 0 file(s)")
        return 0

    failed = False
    for filename in yaml_files:
        path = os.path.join(directory, filename)
        errors = _validate_file(path, schema)
        if errors:
            failed = True
            for error in errors:
                print(f"FAIL {filename}: {error}", file=sys.stderr)
        else:
            print(f"OK   {filename}")

    count = len(yaml_files)
    print(f"Validated {count} file(s)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
