"""Tests for gitweave.apply and gitweave.reset."""
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from gitweave.apply import apply, ApplyResult
from gitweave.managers.org import ORG_DEFAULTS, ResourceStatus
from gitweave.reset import reset, ResetResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def set_prefix(monkeypatch):
    monkeypatch.setenv("FORGE_RESOURCE_PREFIX", "gw-test-")


def _make_team(name: str):
    t = MagicMock()
    t.name = name
    return t


def _make_repo(name: str):
    r = MagicMock()
    r.name = name
    return r


def _make_org(
    teams: list[str] | None = None,
    repos: list[str] | None = None,
    rulesets: list[str] | None = None,
    org_settings: dict | None = None,
):
    """Build a mock PyGithub org object."""
    org = MagicMock()
    org.login = "test-org"

    settings = org_settings or ORG_DEFAULTS.copy()
    org.description = settings.get("description", "")
    org.default_repository_permission = settings.get(
        "default_repository_permission", "read"
    )
    org.web_commit_signoff_required = settings.get(
        "web_commit_signoff_required", False
    )
    org.members_can_create_repositories = settings.get(
        "members_can_create_repositories", True
    )

    team_objs = [_make_team(n) for n in (teams or [])]
    org.get_teams.return_value = team_objs

    repo_objs = [_make_repo(n) for n in (repos or [])]
    org.get_repos.return_value = repo_objs

    ruleset_data = [
        {"name": n, "id": i + 1} for i, n in enumerate(rulesets or [])
    ]

    def _requester(method, path, **kwargs):
        if method == "GET" and "rulesets" in path:
            return ({}, ruleset_data)
        return ({}, {})

    org._requester.requestJsonAndCheck.side_effect = _requester
    return org


@pytest.fixture
def mock_config():
    return {
        "org_settings": {
            "description": "Test org",
            "default_repository_permission": "read",
            "web_commit_signoff_required": False,
            "members_can_create_repositories": True,
        },
        "teams": [{"name": "gw-test-devs", "privacy": "closed"}],
        "repos": [{"slug": "gw-test-repo", "private": True}],
        "rulesets": [{"name": "gw-test-rules"}],
    }


# ---------------------------------------------------------------------------
# reset() tests
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_deletes_all_managed_resources(self):
        """AC4: deletes every prefixed team/repo/ruleset."""
        org = _make_org(
            teams=["gw-test-devs"],
            repos=["gw-test-repo"],
            rulesets=["gw-test-rules"],
        )
        result = reset(org)

        names = {s.name for s in result.statuses}
        assert "gw-test-devs" in names
        assert "gw-test-repo" in names
        assert "gw-test-rules" in names
        assert not result.nothing_changed

    def test_reset_calls_org_reset(self):
        """reset() restores org settings via PATCH /orgs/{org}."""
        org = _make_org(
            org_settings={
                "description": "old",
                "default_repository_permission": "write",
                "web_commit_signoff_required": True,
                "members_can_create_repositories": False,
            }
        )
        reset(org)

        patch_calls = [
            c for c in org._requester.requestJsonAndCheck.call_args_list
            if c[0][0] == "PATCH"
        ]
        assert len(patch_calls) == 1
        _, kwargs = patch_calls[0]
        call_input = kwargs["input"]
        assert call_input["default_repository_permission"] == "read"
        assert call_input["web_commit_signoff_required"] is False

    def test_reset_all_statuses_ok(self):
        """AC4: all statuses are ok after clean reset."""
        org = _make_org(
            teams=["gw-test-devs"],
            repos=["gw-test-repo"],
            rulesets=["gw-test-rules"],
        )
        result = reset(org)
        assert all(s.status == "ok" for s in result.statuses)

    def test_reset_nothing_changed_when_clean(self):
        """AC5: reset on clean org sets nothing_changed=True."""
        org = _make_org()  # defaults, no prefixed resources
        result = reset(org)

        assert result.nothing_changed is True

    def test_reset_idempotent_second_call_nothing_changed(self):
        """AC5: second reset also exits 0 and reports nothing_changed."""
        org = _make_org()
        result1 = reset(org)
        result2 = reset(org)

        assert result1.nothing_changed is True
        assert result2.nothing_changed is True
        assert all(s.status == "ok" for s in result2.statuses)

    def test_reset_404_treated_as_success(self):
        """AC4: 404 on delete treated as success."""
        org = _make_org(teams=["gw-test-devs"])
        # Make the team's delete() raise a 404-like error
        team_mock = _make_team("gw-test-devs")
        team_mock.delete.side_effect = Exception("404 Not Found")
        org.get_teams.return_value = [team_mock]

        result = reset(org)

        team_status = next(s for s in result.statuses if s.name == "gw-test-devs")
        assert team_status.status == "ok"

    def test_reset_requires_prefix_env_var(self, monkeypatch):
        """reset() raises EnvironmentError when neither GW_RESOURCE_PREFIX nor FORGE_RESOURCE_PREFIX is set."""
        monkeypatch.delenv("GW_RESOURCE_PREFIX", raising=False)
        monkeypatch.delenv("FORGE_RESOURCE_PREFIX", raising=False)
        org = _make_org()
        with pytest.raises(EnvironmentError, match="GW_RESOURCE_PREFIX"):
            reset(org)


# ---------------------------------------------------------------------------
# apply() tests
# ---------------------------------------------------------------------------


class TestApply:
    def test_apply_calls_each_manager(self, mock_config):
        """AC1: apply() calls each manager's apply() for every declared resource."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config):
            result = apply(org, json_mode=False)

        assert isinstance(result, ApplyResult)
        # org_settings + 1 team + 1 repo + 1 ruleset = 4 statuses
        assert len(result.statuses) == 4
        assert not result.has_errors
        assert all(s.status == "ok" for s in result.statuses)

    def test_apply_no_state_in_normal_mode(self, mock_config):
        """AC1: state is None when json_mode=False."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config):
            result = apply(org, json_mode=False)

        assert result.state is None

    def test_apply_continues_after_error(self, mock_config):
        """AC2: apply() is best-effort — continues past one resource error."""
        org = _make_org()
        # Make PATCH /orgs/{org} fail (org_settings) but leave GET rulesets intact
        _orig = org._requester.requestJsonAndCheck.side_effect

        def _fail_patch(method, path, **kwargs):
            if method == "PATCH":
                raise Exception("API error")
            return _orig(method, path, **kwargs)

        org._requester.requestJsonAndCheck.side_effect = _fail_patch

        with patch("gitweave.apply.load_config", return_value=mock_config):
            result = apply(org, json_mode=False)

        assert len(result.statuses) == 4
        assert result.has_errors

        org_status = next(s for s in result.statuses if s.name == "org_settings")
        assert org_status.status == "error"
        assert org_status.error is not None

        other = [s for s in result.statuses if s.name != "org_settings"]
        assert all(s.status == "ok" for s in other)

    def test_apply_json_mode_calls_reset_first(self, mock_config):
        """AC3: apply(json_mode=True) calls reset() before applying."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config), \
             patch("gitweave.apply.reset") as mock_reset:
            mock_reset.return_value = ResetResult()
            result = apply(org, json_mode=True)

        mock_reset.assert_called_once_with(org)

    def test_apply_json_mode_returns_state_dict(self, mock_config):
        """AC3: apply(json_mode=True) returns JSON-serialisable state dict."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config), \
             patch("gitweave.apply.reset") as mock_reset:
            mock_reset.return_value = ResetResult()
            result = apply(org, json_mode=True)

        assert result.state is not None
        assert isinstance(result.state, dict)
        # Must be JSON-serialisable (no MagicMock objects leaking in)
        serialised = json.dumps(result.state)
        assert isinstance(serialised, str)

    def test_apply_json_mode_state_has_expected_keys(self, mock_config):
        """AC3: state dict has org_settings, teams, repos, rulesets keys."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config), \
             patch("gitweave.apply.reset") as mock_reset:
            mock_reset.return_value = ResetResult()
            result = apply(org, json_mode=True)

        assert set(result.state.keys()) >= {"org_settings", "teams", "repos", "rulesets"}

    def test_apply_result_has_errors_true(self):
        """has_errors is True when any status is 'error'."""
        r = ApplyResult(
            statuses=[
                ResourceStatus(name="x", status="ok"),
                ResourceStatus(name="y", status="error", error="boom"),
            ]
        )
        assert r.has_errors is True

    def test_apply_result_has_errors_false(self):
        """has_errors is False when all statuses are ok."""
        r = ApplyResult(
            statuses=[ResourceStatus(name="x", status="ok")]
        )
        assert r.has_errors is False

    def test_apply_result_to_json_serialisable(self, mock_config):
        """to_json() returns valid JSON string."""
        org = _make_org()

        with patch("gitweave.apply.load_config", return_value=mock_config):
            result = apply(org, json_mode=False)

        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert "statuses" in parsed
