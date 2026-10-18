"""
Tests for GitWeave Copier modules (offline schema validation only).

These tests do NOT invoke Copier; they validate structure and schema conformance.
Render-time tests live in WI-3.

test_copier_yaml_validates_against_schema and
test_terraform_module_has_input_that_changes_output will fail until
WI-2b delivers the terraform_module — that is expected.
"""

import json
import os
import unittest

import yaml
import jsonschema

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "copier-module.schema.json")
MODULES_DIR = os.path.join(REPO_ROOT, "modules")


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


def _load_copier_yaml(module_name: str) -> dict:
    path = os.path.join(MODULES_DIR, module_name, "copier.yaml")
    with open(path) as fh:
        return yaml.safe_load(fh)


def _questions(doc: dict) -> dict:
    """Return all top-level keys that are not _metadata (i.e. input questions)."""
    return {k: v for k, v in doc.items() if k != "_metadata"}


class TestCopierModules(unittest.TestCase):
    def test_copier_yaml_validates_against_schema(self):
        """Both module copier.yaml files must validate against copier-module.schema.json."""
        schema = _load_schema()
        for module in ("python_service", "terraform_module"):
            with self.subTest(module=module):
                doc = _load_copier_yaml(module)
                jsonschema.validate(instance=doc, schema=schema)

    def test_python_service_has_input_that_changes_output(self):
        """python_service module has >=1 input declared."""
        doc = _load_copier_yaml("python_service")
        questions = _questions(doc)
        self.assertGreaterEqual(
            len(questions),
            1,
            "python_service/copier.yaml must declare at least one input question",
        )

    def test_terraform_module_has_input_that_changes_output(self):
        """terraform_module has >=1 input declared."""
        doc = _load_copier_yaml("terraform_module")
        questions = _questions(doc)
        self.assertGreaterEqual(
            len(questions),
            1,
            "terraform_module/copier.yaml must declare at least one input question",
        )

    def test_module_names_match_directories(self):
        """_metadata.name matches the directory name for each module."""
        for module_dir in os.listdir(MODULES_DIR):
            copier_path = os.path.join(MODULES_DIR, module_dir, "copier.yaml")
            if not os.path.isfile(copier_path):
                continue
            with self.subTest(module=module_dir):
                with open(copier_path) as fh:
                    doc = yaml.safe_load(fh)
                name = doc.get("_metadata", {}).get("name")
                self.assertEqual(
                    name,
                    module_dir,
                    f"_metadata.name '{name}' must match directory name '{module_dir}'",
                )
