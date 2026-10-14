"""tests/test_plan_self_serve.py — self-serve resource type diff tests.

All tests call _diff() directly with in-memory dicts; zero network calls.
Covers AC1-AC5 of WI-8: create/unchanged/delete for self_serve_repo,
policy_exception, and team_membership resource types.
"""

from __future__ import annotations

import pytest

from gitweave.plan import _diff, PlanItem, PlanResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_cfg(**overrides) -> dict:
    """Minimal config dict; override keys via kwargs."""
    base = {
        "org_settings": {},
        "teams": [],
        "repos": [],
        "rulesets": [],
        "self_serve_repos": [],
        "policy_exceptions": [],
        "team_memberships": [],
    }
    base.update(overrides)
    return base


def _base_snapshot(**overrides) -> dict:
    """Minimal snapshot dict; override keys via kwargs."""
    base = {
        "org_settings": {},
        "teams": [],
        "repos": [],
        "rulesets": [],
        "self_serve_repos": [],
        "policy_exceptions": [],
        "team_memberships": [],
    }
    base.update(overrides)
    return base


def _actions(result: PlanResult, resource_type: str) -> dict[str, str]:
    """Return {name: action} for items matching resource_type."""
    return {
        item.name: item.action
        for item in result.items
        if item.resource_type == resource_type
    }


# ---------------------------------------------------------------------------
# TestPlanSelfServe
# ---------------------------------------------------------------------------


class TestPlanSelfServe:
    # AC1: declared repo not in snapshot → create
    def test_self_serve_repo_create_action(self):
        cfg = _base_cfg(self_serve_repos=[{"name": "forge-myrepo"}])
        snap = _base_snapshot()
        result = _diff(cfg, snap, "")
        assert _actions(result, "self_serve_repo") == {"forge-myrepo": "create"}

    # AC2: declared repo exists in both → unchanged
    def test_self_serve_repo_unchanged_action(self):
        cfg = _base_cfg(self_serve_repos=[{"name": "forge-myrepo"}])
        snap = _base_snapshot(self_serve_repos=[{"name": "forge-myrepo"}])
        result = _diff(cfg, snap, "")
        assert _actions(result, "self_serve_repo") == {"forge-myrepo": "unchanged"}

    # AC3: repo in snapshot but removed from policy → delete  [GATE TEST]
    def test_self_serve_repo_delete_action(self):
        cfg = _base_cfg()  # no declared self_serve_repos
        snap = _base_snapshot(self_serve_repos=[{"name": "forge-myrepo"}])
        result = _diff(cfg, snap, "")
        assert _actions(result, "self_serve_repo") == {"forge-myrepo": "delete"}

    # AC4: policy_exception in snapshot but not in policy → delete
    def test_policy_exception_delete_action(self):
        cfg = _base_cfg()
        snap = _base_snapshot(
            policy_exceptions=[{"name": "forge-myrepo/skip-codeowners"}]
        )
        result = _diff(cfg, snap, "")
        assert _actions(result, "policy_exception") == {
            "forge-myrepo/skip-codeowners": "delete"
        }

    # AC5: team_membership declared but not in snapshot → create
    def test_team_membership_create_action(self):
        cfg = _base_cfg(team_memberships=[{"name": "platform/alice"}])
        snap = _base_snapshot()
        result = _diff(cfg, snap, "")
        assert _actions(result, "team_membership") == {"platform/alice": "create"}
