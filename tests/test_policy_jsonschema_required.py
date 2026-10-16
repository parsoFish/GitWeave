"""AC5: jsonschema declared in requirements.txt + pyproject.toml;
policy.py imports it unconditionally; schema-invalid policy rejected.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


_ROOT = Path(__file__).parent.parent


class TestJsonschemaRequired:
    """jsonschema is a hard dependency, not an optional one."""

    def test_jsonschema_declared_in_requirements_txt(self):
        req = (_ROOT / "requirements.txt").read_text()
        assert re.search(r"(?i)^jsonschema", req, re.MULTILINE), \
            "jsonschema not found in requirements.txt"

    def test_jsonschema_declared_in_pyproject_toml(self):
        content = (_ROOT / "pyproject.toml").read_text()
        assert "jsonschema" in content, "jsonschema not declared in pyproject.toml"

    def test_policy_imports_jsonschema_unconditionally(self):
        """policy.py must have a bare 'import jsonschema' with no try/except wrapper."""
        src = (_ROOT / "gitweave" / "policy.py").read_text()
        tree = ast.parse(src)
        # Check for unconditional import at module level (not inside Try node)
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if alias.name == "jsonschema":
                                pytest.fail(
                                    "policy.py imports jsonschema inside a try/except — "
                                    "it must be an unconditional module-level import"
                                )
        # Confirm the unconditional import exists
        found_unconditional = any(
            isinstance(node, ast.Import)
            and any(a.name == "jsonschema" for a in node.names)
            for node in ast.walk(tree)
        )
        assert found_unconditional, "policy.py has no 'import jsonschema' statement"

    def test_no_has_jsonschema_fallback_flag(self):
        """The _HAS_JSONSCHEMA fallback variable must not exist in policy.py."""
        src = (_ROOT / "gitweave" / "policy.py").read_text()
        assert "_HAS_JSONSCHEMA" not in src, \
            "policy.py still contains _HAS_JSONSCHEMA fallback — remove the ImportError path"

    def test_schema_invalid_policy_rejected_with_policy_error(self, tmp_path):
        """A schema-invalid policy.yaml raises PolicyError (wraps ValidationError)."""
        bad = tmp_path / "policy.yaml"
        bad.write_text("teams: not-a-list\n")

        from gitweave.policy import PolicyError, PolicyLoader

        with pytest.raises(PolicyError, match="schema validation failed"):
            PolicyLoader(bad).load()

    def test_valid_policy_loads(self, tmp_path):
        """A well-formed policy loads without error."""
        good = tmp_path / "policy.yaml"
        good.write_text(
            "teams:\n  - slug: eng\n    allowed_request_types:\n      - new-repo\n"
        )
        from gitweave.policy import PolicyLoader

        data = PolicyLoader(good).load()
        assert data["teams"][0]["slug"] == "eng"
