#!/usr/bin/env python3
"""
Validate overlay config files in a directory against schemas/overlay.schema.json.

Usage:
    python3 scripts/validate_overlay_configs.py [config_dir]

Exits 0 if all .yaml files pass schema validation, non-zero if any fail.
"""

import argparse
import concurrent.futures
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import yaml
import jsonschema
from jsonschema import validate, ValidationError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "overlay.schema.json")


def load_schema(schema_path: str) -> dict:
    with open(schema_path) as f:
        return json.load(f)


def _validate_file(filename: str, config_dir: str, schema: dict) -> tuple[str, bool, str]:
    """Validate a single YAML file. Returns (filename, ok, message)."""
    filepath = os.path.join(config_dir, filename)
    try:
        with open(filepath) as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return filename, False, f"YAML parse error — {exc}"

    try:
        validate(instance=doc, schema=schema)
        return filename, True, ""
    except ValidationError as exc:
        return filename, False, exc.message


def validate_directory(config_dir: str, schema: dict) -> bool:
    """Validate all .yaml files in config_dir in parallel. Returns True if all pass."""
    if not os.path.isdir(config_dir):
        print(f"Validated 0 files (directory does not exist: {config_dir})")
        return True

    yaml_files = sorted(
        f for f in os.listdir(config_dir) if f.endswith(".yaml")
    )

    if not yaml_files:
        print("Validated 0 files")
        return True

    results: list[tuple[str, bool, str]] = [None] * len(yaml_files)

    with ThreadPoolExecutor() as executor:
        future_to_index = {
            executor.submit(_validate_file, filename, config_dir, schema): i
            for i, filename in enumerate(yaml_files)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            results[idx] = future.result()

    failures = []
    for filename, ok, message in results:
        if ok:
            print(f"OK   {filename}")
        else:
            print(f"FAIL {filename}: {message}")
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
