"""tests/test_ownership_marker.py — unit tests for GW_RESOURCE_PREFIX ownership marker.

All tests use fixture files or in-memory dicts; zero live network calls.
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest

from gitweave.plan import plan, PlanResult


REPO_ROOT = pathlib.Path(__file__).parent.parent
ORG_EMPTY_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "org-empty.json"

_BASE_ORG_SETTINGS = {
    "description": "",
    "default_repository_permission": "read",
    "web_commit_signoff_required": False,
    "members_can_create_repositories": True,
}


class TestOwnershipMarker:
    """Tests for GW_RESOURCE_PREFIX as primary ownership marker."""

    def test_plan_scopes_by_gw_resource_prefix(self, monkeypatch):
        """AC1: GW_RESOURCE_PREFIX set, FORGE_RESOURCE_PREFIX unset →
        resources scoped to names starting with GW_RESOURCE_PREFIX;
        plan() completes without EnvironmentError and returns a PlanResult.
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
        monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)

        cfg = {
            "org_settings": _BASE_ORG_SETTINGS.copy(),
            "teams": [
                {"name": "gw-test-alpha"},
                {"name": "other-team"},        # outside GW prefix → excluded
            ],
            "repos": [],
            "rulesets": [],
        }

        with patch("gitweave.plan.load_config", return_value=cfg):
            result = plan(fixture_path=str(ORG_EMPTY_FIXTURE))

        assert isinstance(result, PlanResult)

        names_in_result = {item.name for item in result.items}
        assert "gw-test-alpha" in names_in_result, (
            "gw-test-alpha should be included (matches GW_RESOURCE_PREFIX)"
        )
        assert "other-team" not in names_in_result, (
            "other-team should be excluded (does not match GW_RESOURCE_PREFIX)"
        )

    def test_forge_prefix_narrows_scope(self, monkeypatch):
        """AC2: both GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX set,
        FORGE_RESOURCE_PREFIX starts with GW_RESOURCE_PREFIX →
        only resources matching FORGE_RESOURCE_PREFIX are included;
        a resource matching GW_RESOURCE_PREFIX but not FORGE_RESOURCE_PREFIX is absent.
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
        monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "gw-test-narrow-")

        cfg = {
            "org_settings": _BASE_ORG_SETTINGS.copy(),
            "teams": [
                {"name": "gw-test-alpha"},          # matches GW but not FORGE prefix
                {"name": "gw-test-narrow-beta"},    # matches both → included
            ],
            "repos": [],
            "rulesets": [],
        }

        with patch("gitweave.plan.load_config", return_value=cfg):
            result = plan(fixture_path=str(ORG_EMPTY_FIXTURE))

        assert isinstance(result, PlanResult)

        names_in_result = {item.name for item in result.items}
        assert "gw-test-narrow-beta" in names_in_result, (
            "gw-test-narrow-beta should be included (matches FORGE_RESOURCE_PREFIX)"
        )
        assert "gw-test-alpha" not in names_in_result, (
            "gw-test-alpha should be excluded (matches GW but not FORGE prefix)"
        )

    def test_all_resources_included_when_both_prefixes_unset(self, monkeypatch):
        """AC3: GW_RESOURCE_PREFIX and FORGE_RESOURCE_PREFIX both unset →
        prefix is empty string, so all declared resources are included.
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
        monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)

        cfg = {
            "org_settings": _BASE_ORG_SETTINGS.copy(),
            "teams": [
                {"name": "alpha"},
                {"name": "beta"},
            ],
            "repos": [],
            "rulesets": [],
        }

        with patch("gitweave.plan.load_config", return_value=cfg):
            result = plan(fixture_path=str(ORG_EMPTY_FIXTURE))

        assert isinstance(result, PlanResult)

        names_in_result = {item.name for item in result.items}
        assert "alpha" in names_in_result
        assert "beta" in names_in_result
