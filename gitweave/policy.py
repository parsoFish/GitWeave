"""Policy engine for gitweave self-serve requests.

Loads and validates config/policy.yaml, then enforces per-team rules.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any

import jsonschema
import yaml

POLICY_PATH = Path("config/policy.yaml")

POLICY_SCHEMA = {
    "type": "object",
    "required": ["teams"],
    "properties": {
        "teams": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["slug", "allowed_request_types"],
                "properties": {
                    "slug": {"type": "string"},
                    "allowed_request_types": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "allowed_repo_patterns": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "allowed_content_settings": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


class PolicyError(Exception):
    """Raised when the policy file is missing, unparseable, or invalid."""


class PolicyDenied(PolicyError):
    """Raised when a specific request is not permitted by policy."""


class PolicyLoader:
    """Loads and validates config/policy.yaml."""

    def __init__(self, policy_path: Path | str = POLICY_PATH) -> None:
        self._path = Path(policy_path)

    def load(self) -> dict[str, Any]:
        """Load and validate policy YAML.

        Raises:
            PolicyError: if the file is absent, not valid YAML, or fails schema validation.
        """
        if not self._path.exists():
            raise PolicyError(
                f"Policy file not found: {self._path}. "
                "Create config/policy.yaml to define team permissions."
            )

        raw = self._path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise PolicyError(f"Failed to parse {self._path}: {exc}") from exc

        if data is None:
            raise PolicyError(
                f"{self._path} is empty; expected a mapping with a 'teams' key."
            )

        try:
            jsonschema.validate(data, POLICY_SCHEMA)
        except jsonschema.ValidationError as exc:
            raise PolicyError(
                f"Policy schema validation failed: {exc.message}"
            ) from exc

        return data


def check_permission(
    policy: dict[str, Any],
    team: str,
    request_type: str,
    repo_name: str | None = None,
) -> bool:
    """Check whether *team* may perform *request_type* (optionally on *repo_name*).

    Returns True if the request is allowed.

    Raises:
        PolicyDenied: with a specific rule-name message if any check fails.
    """
    teams: list[dict] = policy.get("teams", [])
    team_cfg = next((t for t in teams if t.get("slug") == team), None)

    if team_cfg is None:
        raise PolicyDenied(
            f"Team '{team}' has no declared permissions in policy.yaml. "
            "Add an entry for this team before submitting self-serve requests."
        )

    allowed_types: list[str] = team_cfg.get("allowed_request_types", [])
    if request_type not in allowed_types:
        raise PolicyDenied(
            f"{request_type} not in {team}.allowed_request_types"
        )

    if repo_name is not None:
        patterns: list[str] = team_cfg.get("allowed_repo_patterns", [])
        if not patterns:
            raise PolicyDenied(
                f"{team}.allowed_repo_patterns is empty or absent; "
                f"repo-name requests are denied by default (fail-closed): {patterns}"
            )
        if not any(fnmatch.fnmatch(repo_name, p) for p in patterns):
            raise PolicyDenied(
                f"repo_name '{repo_name}' does not match any pattern in "
                f"{team}.allowed_repo_patterns: {patterns}"
            )

    return True
