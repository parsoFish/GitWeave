"""
WI-15 K3c: Offline render of terraform_module with a non-default module_name.

GIVEN terraform_module
WHEN gw module render terraform_module --dest <tmp> runs offline with a non-default module_name
THEN the rendered main.tf and CI workflow contain that module_name and the CI workflow
     parses as valid YAML.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from gitweave.module_render import render_module

MODULE_NAME = "my_vpc_baseline"


class TestTerraformModuleRender:
    """K3c acceptance tests for terraform_module offline rendering."""

    def test_rendered_main_tf_contains_module_name(self) -> None:
        """Rendered main.tf embeds the non-default module_name."""
        with tempfile.TemporaryDirectory() as tmp:
            render_module(
                "terraform_module",
                tmp,
                data={"module_name": MODULE_NAME},
            )
            main_tf = Path(tmp) / "terraform" / "main.tf"
            assert main_tf.exists(), f"main.tf not rendered at {main_tf}"
            content = main_tf.read_text(encoding="utf-8")
            assert MODULE_NAME in content, (
                f"module_name '{MODULE_NAME}' not found in main.tf:\n{content}"
            )

    def test_rendered_ci_workflow_contains_module_name(self) -> None:
        """Rendered CI workflow embeds the non-default module_name."""
        with tempfile.TemporaryDirectory() as tmp:
            render_module(
                "terraform_module",
                tmp,
                data={"module_name": MODULE_NAME},
            )
            workflow = Path(tmp) / ".github" / "workflows" / "ci.yml"
            assert workflow.exists(), f"CI workflow not rendered at {workflow}"
            content = workflow.read_text(encoding="utf-8")
            assert MODULE_NAME in content, (
                f"module_name '{MODULE_NAME}' not found in CI workflow:\n{content}"
            )

    def test_rendered_ci_workflow_is_valid_yaml(self) -> None:
        """Rendered CI workflow parses as valid YAML."""
        with tempfile.TemporaryDirectory() as tmp:
            render_module(
                "terraform_module",
                tmp,
                data={"module_name": MODULE_NAME},
            )
            workflow = Path(tmp) / ".github" / "workflows" / "ci.yml"
            assert workflow.exists(), f"CI workflow not rendered at {workflow}"
            content = workflow.read_text(encoding="utf-8")
            parsed = yaml.safe_load(content)
            assert isinstance(parsed, dict), (
                f"CI workflow did not parse as a YAML mapping:\n{content}"
            )
