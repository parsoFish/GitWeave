import os
import unittest

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestExampleTemplateRemoved(unittest.TestCase):
    def test_config_does_not_reference_example_template(self):
        """config/repos/example.yaml must not list example-template after WI-1 deletion."""
        config_path = os.path.join(REPO_ROOT, "config", "repos", "example.yaml")
        self.assertTrue(os.path.isfile(config_path), "config/repos/example.yaml is missing")
        with open(config_path) as f:
            content = f.read()
        self.assertNotIn(
            "example-template",
            content,
            "config/repos/example.yaml still references example-template",
        )

    def test_ci_yaml_does_not_assert_example_template_in_smoke(self):
        """ci.yaml smoke step must not assert example-template in dry-run output."""
        ci_path = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yaml")
        self.assertTrue(os.path.isfile(ci_path), ".github/workflows/ci.yaml is missing")
        with open(ci_path) as f:
            content = f.read()
        # After deletion, the smoke step must not grep for this string
        self.assertNotIn(
            "example-template",
            content,
            "ci.yaml still asserts 'example-template' in smoke check — remove that assertion",
        )
