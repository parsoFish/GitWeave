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

    def test_forge_prefix_not_starting_with_gw_prefix_is_refused(self, monkeypatch):
        """AC2: FORGE_RESOURCE_PREFIX doesn't start with GW_RESOURCE_PREFIX →
        EnvironmentError raised naming FORGE_RESOURCE_PREFIX, nothing changed.
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
        monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "unrelated-prefix-")

        cfg = {
            "org_settings": _BASE_ORG_SETTINGS.copy(),
            "teams": [{"name": "gw-test-alpha"}],
            "repos": [],
            "rulesets": [],
        }

        with patch("gitweave.plan.load_config", return_value=cfg):
            with pytest.raises(EnvironmentError, match="FORGE_RESOURCE_PREFIX"):
                plan(fixture_path=str(ORG_EMPTY_FIXTURE))

    def test_gw_resource_prefix_required_when_no_forge_prefix(self, monkeypatch):
        """AC1: GW_RESOURCE_PREFIX unset and FORGE_RESOURCE_PREFIX unset →
        managers raise EnvironmentError mentioning GW_RESOURCE_PREFIX.
        """
        from unittest.mock import MagicMock

        from gitweave.managers.teams import TeamsManager
        from gitweave.managers.repos import ReposManager
        from gitweave.managers.rulesets import RulesetsManager

        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
        monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)

        org = MagicMock()
        for Manager in (TeamsManager, ReposManager, RulesetsManager):
            with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
                Manager(org)

    def test_managers_work_with_only_gw_resource_prefix(self, monkeypatch):
        """AC1: GW_RESOURCE_PREFIX set alone → managers initialise without error
        and list_managed() returns only prefixed resources.
        """
        from unittest.mock import MagicMock

        from gitweave.managers.teams import TeamsManager

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
        monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)

        org = MagicMock()
        team_a = MagicMock()
        team_a.name = "gw-test-alpha"
        team_b = MagicMock()
        team_b.name = "other-team"
        org.get_teams.return_value = [team_a, team_b]

        mgr = TeamsManager(org)
        managed = mgr.list_managed()
        assert len(managed) == 1
        assert managed[0].name == "gw-test-alpha"

    def test_managers_refuse_mismatched_forge_prefix(self, monkeypatch):
        """AC2: FORGE_RESOURCE_PREFIX doesn't start with GW_RESOURCE_PREFIX →
        manager __init__ raises EnvironmentError naming FORGE_RESOURCE_PREFIX.
        """
        from unittest.mock import MagicMock

        from gitweave.managers.teams import TeamsManager

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")
        monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "bad-prefix-")

        org = MagicMock()
        with pytest.raises(EnvironmentError, match="FORGE_RESOURCE_PREFIX"):
            TeamsManager(org)
