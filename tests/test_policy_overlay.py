"""Tests for policy overlay extensions — allowed_modules and PolicyError contract.

Covers:
- AC2: PolicyLoader exposes per-team allowed_modules; invalid policy fails at load time
- AC3: Absent config/policy.yaml raises PolicyError (not FileNotFoundError)
- AC4: schemas/policy.schema.json validates config/policy.yaml

None of these tests inherit any GW_* autouse fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from gitweave.policy import PolicyError, PolicyLoader

_REPO_ROOT = Path(__file__).parent.parent


def _write_policy(tmp_path: Path, content: str) -> PolicyLoader:
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(content, encoding="utf-8")
    return PolicyLoader(policy_path=policy_file)


_VALID_POLICY_YAML = """\
teams:
  - slug: example-team
    allowed_request_types:
      - new-repo
    allowed_modules:
      - python_service
  - slug: another-team
    allowed_request_types:
      - new-repo
    allowed_modules:
      - terraform_module
"""

_INVALID_POLICY_YAML = """\
not_teams:
  - slug: oops
"""


class TestPolicyOverlay:
    """Tests for allowed_modules support in PolicyLoader."""

    def test_allowed_modules_loaded(self, tmp_path: Path) -> None:
        """PolicyLoader.allowed_modules_for_team returns the declared module list."""
        loader = _write_policy(tmp_path, _VALID_POLICY_YAML)
        modules = loader.allowed_modules_for_team("example-team")
        assert modules == ["python_service"]

    def test_second_team_allowed_modules_loaded(self, tmp_path: Path) -> None:
        """A second team's allowed_modules list is independently returned."""
        loader = _write_policy(tmp_path, _VALID_POLICY_YAML)
        modules = loader.allowed_modules_for_team("another-team")
        assert modules == ["terraform_module"]

    def test_team_not_in_policy_returns_empty(self, tmp_path: Path) -> None:
        """allowed_modules_for_team returns [] when the team slug is absent."""
        loader = _write_policy(tmp_path, _VALID_POLICY_YAML)
        assert loader.allowed_modules_for_team("unknown-team") == []

    def test_team_without_allowed_modules_returns_empty(self, tmp_path: Path) -> None:
        """A team entry with no allowed_modules key returns an empty list."""
        policy = """\
teams:
  - slug: bare-team
    allowed_request_types:
      - new-repo
"""
        loader = _write_policy(tmp_path, policy)
        assert loader.allowed_modules_for_team("bare-team") == []

    def test_policy_absent_raises_policy_error(self, tmp_path: Path) -> None:
        """Absent policy.yaml raises PolicyError, not FileNotFoundError."""
        loader = PolicyLoader(policy_path=tmp_path / "missing.yaml")
        with pytest.raises(PolicyError):
            loader.allowed_modules_for_team("any-team")

    def test_policy_absent_not_file_not_found_error(self, tmp_path: Path) -> None:
        """The raised exception is PolicyError, never bare FileNotFoundError."""
        loader = PolicyLoader(policy_path=tmp_path / "missing.yaml")
        with pytest.raises(PolicyError):
            loader.load()
        # ensure FileNotFoundError is not raised directly
        try:
            loader.load()
        except PolicyError:
            pass
        except FileNotFoundError as exc:
            pytest.fail(f"FileNotFoundError leaked: {exc}")

    def test_policy_absent_error_names_policy_rule(self, tmp_path: Path) -> None:
        """The PolicyError message names the policy rule (file path or rule label)."""
        loader = PolicyLoader(policy_path=tmp_path / "policy.yaml")
        with pytest.raises(PolicyError, match="policy"):
            loader.load()

    def test_invalid_policy_yaml_raises_at_load(self, tmp_path: Path) -> None:
        """A policy.yaml that fails schema validation raises PolicyError at load."""
        loader = _write_policy(tmp_path, _INVALID_POLICY_YAML)
        with pytest.raises(PolicyError):
            loader.load()

    def test_policy_schema_validates_config_policy_yaml(self) -> None:
        """schemas/policy.schema.json validates config/policy.yaml without errors."""
        schema_path = _REPO_ROOT / "schemas" / "policy.schema.json"
        policy_path = _REPO_ROOT / "config" / "policy.yaml"

        with open(schema_path) as f:
            schema = json.load(f)
        with open(policy_path) as f:
            policy_data = yaml.safe_load(f)

        # Should not raise
        jsonschema.validate(policy_data, schema)
