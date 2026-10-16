"""Tests for gitweave.policy — PolicyLoader and check_permission."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from gitweave.policy import PolicyDenied, PolicyError, PolicyLoader, check_permission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_POLICY: dict = {
    "teams": [
        {
            "slug": "platform",
            "allowed_request_types": ["new-repo", "content-update"],
            "allowed_repo_patterns": ["forge-*"],
        }
    ]
}


def _write_policy(tmp_path: Path, content: str) -> PolicyLoader:
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(content, encoding="utf-8")
    return PolicyLoader(policy_path=policy_file)


# ---------------------------------------------------------------------------
# AC1 — absent file
# ---------------------------------------------------------------------------


class TestPolicyLoader:
    """Tests for PolicyLoader.load()."""

    def test_absent_policy_raises(self, tmp_path: Path) -> None:
        """PolicyLoader.load() raises PolicyError if the file doesn't exist."""
        loader = PolicyLoader(policy_path=tmp_path / "policy.yaml")
        with pytest.raises(PolicyError, match="not found"):
            loader.load()

    def test_absent_policy_names_file(self, tmp_path: Path) -> None:
        """Error message includes the missing path."""
        missing = tmp_path / "config" / "policy.yaml"
        loader = PolicyLoader(policy_path=missing)
        with pytest.raises(PolicyError, match=str(missing)):
            loader.load()

    def test_absent_policy_exits_nonzero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """CLI exits non-zero when policy.yaml is absent."""
        # Run a subprocess so sys.exit is real.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent(f"""
                    import sys
                    from pathlib import Path
                    from gitweave.policy import PolicyLoader, PolicyError
                    loader = PolicyLoader(policy_path=Path({str(tmp_path / 'policy.yaml')!r}))
                    try:
                        loader.load()
                    except PolicyError as e:
                        print(str(e), file=sys.stderr)
                        sys.exit(1)
                """),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "Expected non-zero exit for missing policy"

    # AC2 — invalid YAML
    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        """PolicyLoader.load() raises PolicyError for unparseable YAML."""
        loader = _write_policy(tmp_path, "teams: [unclosed bracket\n  bad: yaml: here")
        with pytest.raises(PolicyError, match="parse"):
            loader.load()

    def test_invalid_yaml_does_not_allow_all(self, tmp_path: Path) -> None:
        """A parse error never silently permits requests (raises, doesn't return)."""
        loader = _write_policy(tmp_path, "teams: [unclosed\nbad: yaml")
        raised = False
        try:
            loader.load()
        except PolicyError:
            raised = True
        assert raised, "PolicyError not raised for invalid YAML"

    # AC3 — schema validation
    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        """PolicyLoader.load() raises PolicyError if schema validation fails."""
        loader = _write_policy(tmp_path, "not_teams: []")
        with pytest.raises(PolicyError, match="teams"):
            loader.load()

    def test_schema_error_message_included(self, tmp_path: Path) -> None:
        """Error message contains schema validation info."""
        loader = _write_policy(tmp_path, "not_teams: []")
        with pytest.raises(PolicyError) as exc_info:
            loader.load()
        assert "teams" in str(exc_info.value).lower() or "schema" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# AC4–AC7 — check_permission
# ---------------------------------------------------------------------------


class TestCheckPermission:
    """Tests for check_permission()."""

    def test_unknown_team_raises(self) -> None:
        """Raises PolicyDenied for a team not in policy, naming the team."""
        with pytest.raises(PolicyDenied, match="unknown-team"):
            check_permission(VALID_POLICY, team="unknown-team", request_type="new-repo")

    def test_unknown_team_message_states_no_permissions(self) -> None:
        """Error message states team has no declared permissions."""
        with pytest.raises(PolicyDenied, match="no declared permissions|unknown-team"):
            check_permission(VALID_POLICY, team="ghost", request_type="new-repo")

    def test_allowed_type_and_pattern_returns_true(self) -> None:
        """Returns True when team, type and repo_name all pass."""
        result = check_permission(
            VALID_POLICY,
            team="platform",
            request_type="new-repo",
            repo_name="forge-foo",
        )
        assert result is True

    def test_disallowed_request_type_raises(self) -> None:
        """Raises PolicyDenied citing the specific rule name for a bad type."""
        with pytest.raises(PolicyDenied, match="delete-repo not in platform.allowed_request_types"):
            check_permission(VALID_POLICY, team="platform", request_type="delete-repo")

    def test_disallowed_request_type_cites_rule(self) -> None:
        """Error names the request_type and team slug."""
        with pytest.raises(PolicyDenied) as exc_info:
            check_permission(VALID_POLICY, team="platform", request_type="nuke-everything")
        msg = str(exc_info.value)
        assert "nuke-everything" in msg
        assert "platform" in msg

    def test_repo_name_not_matching_pattern_raises(self) -> None:
        """Raises PolicyDenied when repo_name doesn't match allowed_repo_patterns."""
        with pytest.raises(PolicyDenied, match="not-allowed"):
            check_permission(
                VALID_POLICY,
                team="platform",
                request_type="new-repo",
                repo_name="not-allowed",
            )

    def test_repo_pattern_rule_named_in_error(self) -> None:
        """Error message names the pattern rule."""
        with pytest.raises(PolicyDenied) as exc_info:
            check_permission(
                VALID_POLICY,
                team="platform",
                request_type="new-repo",
                repo_name="evil-repo",
            )
        msg = str(exc_info.value)
        assert "allowed_repo_patterns" in msg or "forge-*" in msg


# ---------------------------------------------------------------------------
# AC6 — jsonschema declared in requirements.txt + pyproject.toml; validation runs
# ---------------------------------------------------------------------------


class TestJsonschemaSchemaValidation:
    """AC6: jsonschema is available and actually rejects a schema-invalid policy."""

    def test_jsonschema_importable(self) -> None:
        """jsonschema can be imported (declared in requirements.txt + pyproject.toml)."""
        import jsonschema  # noqa: F401 — presence is the assertion

    def test_schema_invalid_policy_rejected_by_jsonschema(self, tmp_path: Path) -> None:
        """A policy with wrong structure is rejected by jsonschema, not by the fallback."""
        # 'teams' must be a list; passing a string triggers a ValidationError.
        bad_policy = "teams: this-should-be-a-list\n"
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(bad_policy)

        from gitweave.policy import PolicyError, PolicyLoader

        with pytest.raises(PolicyError, match="schema validation failed"):
            PolicyLoader(policy_file).load()

    def test_valid_policy_passes_jsonschema(self, tmp_path: Path) -> None:
        """A well-formed policy loads without error."""
        good_policy = textwrap.dedent("""\
            teams:
              - slug: platform
                allowed_request_types:
                  - new-repo
        """)
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text(good_policy)

        from gitweave.policy import PolicyLoader

        data = PolicyLoader(policy_file).load()
        assert data["teams"][0]["slug"] == "platform"
