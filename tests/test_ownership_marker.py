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
    """Tests for GW_RESOURCE_PREFIX as ownership marker."""

    def test_plan_scopes_by_gw_resource_prefix(self, monkeypatch):
        """AC1: GW_RESOURCE_PREFIX set → resources scoped to names starting with that prefix;
        plan() completes without EnvironmentError and returns a PlanResult.
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")

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

    def test_all_resources_included_when_gw_prefix_unset(self, monkeypatch):
        """GW_RESOURCE_PREFIX unset → prefix is empty string, so all declared resources
        are included (plan does not raise; managers would raise if invoked live).
        """
        assert ORG_EMPTY_FIXTURE.exists(), "tests/fixtures/org-empty.json must exist"

        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)

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

    def test_gw_resource_prefix_required_by_managers(self, monkeypatch):
        """GW_RESOURCE_PREFIX unset → managers raise EnvironmentError mentioning
        GW_RESOURCE_PREFIX.
        """
        from unittest.mock import MagicMock

        from gitweave.managers.teams import TeamsManager
        from gitweave.managers.repos import ReposManager
        from gitweave.managers.rulesets import RulesetsManager

        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)

        org = MagicMock()
        for Manager in (TeamsManager, ReposManager, RulesetsManager):
            with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
                Manager(org)

    def test_managers_work_with_gw_resource_prefix(self, monkeypatch):
        """GW_RESOURCE_PREFIX set → managers initialise without error and
        list_managed() returns only prefixed resources.
        """
        from unittest.mock import MagicMock

        from gitweave.managers.teams import TeamsManager

        monkeypatch.setenv("GW_RESOURCE_PREFIX", "gw-test-")

        org = MagicMock()
        team_a = MagicMock()
        team_a.name = "gw-test-alpha"
        team_b = MagicMock()
        team_b.name = "other-team"
        org.get_teams.return_value = [team_a, team_b]

        mgr = TeamsManager(org)
        assert mgr._prefix == "gw-test-"
        managed = mgr.list_managed()
        assert len(managed) == 1
        assert managed[0].name == "gw-test-alpha"
