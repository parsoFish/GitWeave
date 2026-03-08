"""
Unit tests for config/repos/gitweave.yaml — the GitWeave self-hosting overlay config.

This file is the TDD red phase for the self-hosting overlay work item. Every test
will fail until config/repos/gitweave.yaml is created with correct content.

These tests verify that:

  File existence and parseability:
    - config/repos/gitweave.yaml exists
    - The file parses as valid YAML
    - The parsed document is a mapping (dict)

  Schema compliance:
    - The config passes schemas/overlay.schema.json Draft 7 validation
    - apiVersion is exactly 'gitweave.io/v1'
    - kind is exactly 'RepositoryOverlay'
    - metadata.name is a non-empty string

  Repository field:
    - spec.repository is present and non-empty
    - spec.repository matches the owner/repo pattern (exactly one slash)
    - The repo component of spec.repository is 'GitWeave' (correct capitalisation)
    - The owner component is non-empty (org is declared)

  Module references:
    - spec.modules contains at least one entry
    - Every module name in spec.modules corresponds to a directory under modules/
    - Each module entry has a non-empty 'name' field

  Branch protection:
    - At least one environment in spec.environments declares protection_rules
    - The declared protection_rules includes required_reviewers >= 1
    - The declared protection_rules includes required_status_checks with at least one entry

  Team ownership:
    - spec.variables.team_name is present and non-empty
    - spec.variables.team_name matches a team slug declared in config/teams.yaml

  README self-hosting documentation:
    - README.md contains a 'Self-Hosting' section heading
"""

import json
import os
import unittest

import jsonschema
import yaml
from jsonschema import validate, ValidationError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OVERLAY_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "repos", "gitweave.yaml")
SCHEMA_PATH = os.path.join(REPO_ROOT, "schemas", "overlay.schema.json")
TEAMS_CONFIG_PATH = os.path.join(REPO_ROOT, "config", "teams.yaml")
MODULES_DIR = os.path.join(REPO_ROOT, "modules")
README_PATH = os.path.join(REPO_ROOT, "README.md")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    """Load and return the overlay JSON Schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _load_overlay() -> dict:
    """Load and return the gitweave.yaml overlay config as a Python dict."""
    with open(OVERLAY_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _load_teams() -> dict:
    """Load and return config/teams.yaml as a Python dict."""
    with open(TEAMS_CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# TestOverlayFileExistsAndParseable
# ---------------------------------------------------------------------------


class TestOverlayFileExistsAndParseable(unittest.TestCase):
    """Sanity checks: the file exists, is valid YAML, and decodes to a mapping."""

    def test_gitweave_yaml_exists_in_config_repos(self):
        """config/repos/gitweave.yaml must exist — it is the self-hosting overlay."""
        self.assertTrue(
            os.path.isfile(OVERLAY_CONFIG_PATH),
            f"config/repos/gitweave.yaml is missing — expected at {OVERLAY_CONFIG_PATH}. "
            "Create this file to enable GitWeave self-hosting.",
        )

    def test_gitweave_yaml_is_parseable_yaml(self):
        """config/repos/gitweave.yaml must parse without a YAML syntax error."""
        with open(OVERLAY_CONFIG_PATH) as f:
            try:
                doc = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                self.fail(
                    f"config/repos/gitweave.yaml has a YAML syntax error: {exc}"
                )
        self.assertIsNotNone(doc, "config/repos/gitweave.yaml parsed to None (empty file?)")

    def test_gitweave_yaml_parses_as_mapping(self):
        """The parsed document must be a mapping (dict), not a list or scalar."""
        doc = _load_overlay()
        self.assertIsInstance(
            doc,
            dict,
            "config/repos/gitweave.yaml did not parse as a YAML mapping. "
            "The file must be a RepositoryOverlay object, not a list or scalar.",
        )


# ---------------------------------------------------------------------------
# TestSchemaCompliance
# ---------------------------------------------------------------------------


class TestSchemaCompliance(unittest.TestCase):
    """config/repos/gitweave.yaml must pass schemas/overlay.schema.json validation."""

    def setUp(self):
        self.schema = _load_schema()

    def test_gitweave_overlay_passes_schema_validation(self):
        """The complete overlay config must satisfy the overlay JSON Schema Draft 7."""
        doc = _load_overlay()
        try:
            validate(instance=doc, schema=self.schema)
        except ValidationError as exc:
            self.fail(
                f"config/repos/gitweave.yaml failed schema validation: {exc.message}\n"
                f"Path: {list(exc.absolute_path)}"
            )

    def test_apiVersion_is_gitweave_io_v1(self):
        """apiVersion must be exactly 'gitweave.io/v1'."""
        doc = _load_overlay()
        self.assertEqual(
            doc.get("apiVersion"),
            "gitweave.io/v1",
            f"apiVersion is {doc.get('apiVersion')!r} — must be 'gitweave.io/v1'",
        )

    def test_kind_is_RepositoryOverlay(self):
        """kind must be exactly 'RepositoryOverlay'."""
        doc = _load_overlay()
        self.assertEqual(
            doc.get("kind"),
            "RepositoryOverlay",
            f"kind is {doc.get('kind')!r} — must be 'RepositoryOverlay'",
        )

    def test_metadata_name_is_non_empty_string(self):
        """metadata.name must be a non-empty string."""
        doc = _load_overlay()
        name = doc.get("metadata", {}).get("name")
        self.assertIsInstance(
            name,
            str,
            f"metadata.name is {name!r} — must be a string",
        )
        self.assertGreater(
            len(name),
            0,
            "metadata.name must not be empty",
        )


# ---------------------------------------------------------------------------
# TestRepositoryField
# ---------------------------------------------------------------------------


class TestRepositoryField(unittest.TestCase):
    """spec.repository must be 'owner/GitWeave' in the correct format."""

    def setUp(self):
        self.doc = _load_overlay()
        self.repository = self.doc.get("spec", {}).get("repository", "")

    def test_spec_repository_is_present(self):
        """spec.repository must be present and non-empty."""
        self.assertTrue(
            self.repository,
            "spec.repository is missing or empty — it must be set to 'owner/GitWeave'",
        )

    def test_spec_repository_matches_owner_slash_repo_pattern(self):
        """spec.repository must match the owner/repo pattern (exactly one slash)."""
        import re
        self.assertRegex(
            self.repository,
            r"^[^/\s]+/[^/\s]+$",
            f"spec.repository '{self.repository}' does not match owner/repo format. "
            "Use a value like 'my-org/GitWeave'.",
        )

    def test_spec_repository_repo_component_is_GitWeave(self):
        """The repo component (after the slash) must be 'GitWeave' (case-sensitive)."""
        parts = self.repository.split("/", 1)
        repo_component = parts[1] if len(parts) == 2 else ""
        self.assertEqual(
            repo_component,
            "GitWeave",
            f"spec.repository repo component is '{repo_component}' — must be 'GitWeave'. "
            f"Full value: '{self.repository}'",
        )

    def test_spec_repository_owner_component_is_non_empty(self):
        """The owner component (before the slash) must be non-empty."""
        parts = self.repository.split("/", 1)
        owner_component = parts[0] if parts else ""
        self.assertTrue(
            owner_component,
            f"spec.repository owner component is empty in '{self.repository}' — "
            "provide the GitHub organisation or user that owns the GitWeave repository.",
        )

    def test_spec_repository_has_no_more_than_one_slash(self):
        """spec.repository must contain exactly one slash (owner/repo, not org/owner/repo)."""
        slash_count = self.repository.count("/")
        self.assertEqual(
            slash_count,
            1,
            f"spec.repository '{self.repository}' contains {slash_count} slashes — "
            "must contain exactly one slash in owner/repo format.",
        )


# ---------------------------------------------------------------------------
# TestModuleReferences
# ---------------------------------------------------------------------------


class TestModuleReferences(unittest.TestCase):
    """spec.modules must reference at least one existing module from the modules/ directory."""

    def setUp(self):
        self.doc = _load_overlay()
        self.modules = self.doc.get("spec", {}).get("modules", [])

    def test_spec_modules_contains_at_least_one_entry(self):
        """spec.modules must have at least one module entry."""
        self.assertGreater(
            len(self.modules),
            0,
            "spec.modules is empty or missing — declare at least one module to apply "
            "to the GitWeave repository.",
        )

    def test_every_module_entry_has_a_non_empty_name(self):
        """Every item in spec.modules must have a non-empty 'name' field."""
        for i, module in enumerate(self.modules):
            name = module.get("name", "")
            self.assertTrue(
                name,
                f"spec.modules[{i}] has a missing or empty 'name' field. "
                f"Module entry: {module!r}",
            )

    def test_every_module_name_corresponds_to_existing_directory(self):
        """
        Every module name in spec.modules must have a corresponding directory
        under modules/ so that apply-overlays.py can locate the copier template.
        """
        available_modules = {
            entry
            for entry in os.listdir(MODULES_DIR)
            if os.path.isdir(os.path.join(MODULES_DIR, entry))
            and not entry.startswith("_")
            and not entry.startswith(".")
        }
        for module in self.modules:
            name = module.get("name", "")
            if not name:
                continue
            self.assertIn(
                name,
                available_modules,
                f"Module '{name}' referenced in spec.modules does not exist under modules/. "
                f"Available modules: {sorted(available_modules)}",
            )


# ---------------------------------------------------------------------------
# TestBranchProtection
# ---------------------------------------------------------------------------


class TestBranchProtection(unittest.TestCase):
    """
    Branch protection must be configured for at least one environment with:
      - required_reviewers >= 1 (at least one PR review required)
      - required_status_checks listing at least one CI check
    """

    def setUp(self):
        self.doc = _load_overlay()
        self.environments = self.doc.get("spec", {}).get("environments", {})

    def test_spec_environments_is_declared(self):
        """spec.environments must be present to hold branch protection rules."""
        self.assertIsInstance(
            self.environments,
            dict,
            "spec.environments is missing — branch protection rules must be configured "
            "under spec.environments.<env>.protection_rules",
        )
        self.assertGreater(
            len(self.environments),
            0,
            "spec.environments is empty — at least one environment with branch protection "
            "must be declared.",
        )

    def test_at_least_one_environment_declares_protection_rules(self):
        """At least one environment entry must include a protection_rules object."""
        envs_with_protection = [
            env_name
            for env_name, env_config in self.environments.items()
            if isinstance(env_config, dict) and env_config.get("protection_rules")
        ]
        self.assertGreater(
            len(envs_with_protection),
            0,
            f"No environment in spec.environments declares protection_rules. "
            f"Environments found: {list(self.environments.keys())}. "
            "Add protection_rules to at least one environment.",
        )

    def test_branch_protection_requires_at_least_one_pr_review(self):
        """
        The protection_rules for at least one environment must include
        required_reviewers >= 1 to enforce PR review before merging.
        """
        found_valid = False
        for env_name, env_config in self.environments.items():
            if not isinstance(env_config, dict):
                continue
            rules = env_config.get("protection_rules", {})
            if not isinstance(rules, dict):
                continue
            required_reviewers = rules.get("required_reviewers", 0)
            if isinstance(required_reviewers, int) and required_reviewers >= 1:
                found_valid = True
                break

        self.assertTrue(
            found_valid,
            "No environment protection_rules declares required_reviewers >= 1. "
            "Branch protection must require at least one PR review before merging.",
        )

    def test_branch_protection_requires_ci_status_checks(self):
        """
        The protection_rules for at least one environment must declare
        required_status_checks with at least one CI check entry.
        """
        found_valid = False
        for env_name, env_config in self.environments.items():
            if not isinstance(env_config, dict):
                continue
            rules = env_config.get("protection_rules", {})
            if not isinstance(rules, dict):
                continue
            # Accept either required_status_checks or required_checks as the field name
            checks = rules.get("required_status_checks") or rules.get("required_checks") or []
            if isinstance(checks, list) and len(checks) >= 1:
                found_valid = True
                break

        self.assertTrue(
            found_valid,
            "No environment protection_rules declares required_status_checks "
            "(or required_checks) with at least one CI check. "
            "Branch protection must require CI to pass before merging.",
        )


# ---------------------------------------------------------------------------
# TestTeamOwnership
# ---------------------------------------------------------------------------


class TestTeamOwnership(unittest.TestCase):
    """
    Team ownership must be declared via spec.variables.team_name and must
    reference a team slug that exists in config/teams.yaml.
    """

    def setUp(self):
        self.doc = _load_overlay()
        self.variables = self.doc.get("spec", {}).get("variables", {})

    def test_spec_variables_team_name_is_declared(self):
        """spec.variables.team_name must be present and non-empty."""
        team_name = self.variables.get("team_name", "")
        self.assertTrue(
            team_name,
            "spec.variables.team_name is missing or empty. "
            "Declare the owning team slug so GitWeave can enforce team-based access control. "
            "The value must match a team slug in config/teams.yaml.",
        )

    def test_spec_variables_team_name_is_a_string(self):
        """spec.variables.team_name must be a string (not a number or bool)."""
        team_name = self.variables.get("team_name")
        self.assertIsInstance(
            team_name,
            str,
            f"spec.variables.team_name is {team_name!r} — must be a string team slug.",
        )

    def test_spec_variables_team_name_maps_to_team_in_teams_yaml(self):
        """
        spec.variables.team_name must match a team slug declared in config/teams.yaml.

        This ensures the owning team is managed by GitWeave and not a phantom reference.
        """
        team_name = self.variables.get("team_name", "")
        teams_doc = _load_teams()
        declared_teams = teams_doc.get("teams", [])
        declared_slugs = {t.get("name") for t in declared_teams if t.get("name")}

        self.assertIn(
            team_name,
            declared_slugs,
            f"spec.variables.team_name '{team_name}' does not match any team slug "
            f"in config/teams.yaml. Declared teams: {sorted(declared_slugs)}. "
            "Either add the team to config/teams.yaml or update team_name to an existing slug.",
        )


# ---------------------------------------------------------------------------
# TestReadmeSelfHostingSection
# ---------------------------------------------------------------------------


class TestReadmeSelfHostingSection(unittest.TestCase):
    """README.md must contain a 'Self-Hosting' section documenting this capability."""

    def test_readme_exists(self):
        """README.md must exist at the repository root."""
        self.assertTrue(
            os.path.isfile(README_PATH),
            f"README.md is missing — expected at {README_PATH}",
        )

    def test_readme_contains_self_hosting_heading(self):
        """
        README.md must contain a 'Self-Hosting' heading (## Self-Hosting or similar).

        This documents how GitWeave manages its own control repository via its
        overlay system — demonstrating the self-hosting capability to users.
        """
        with open(README_PATH) as f:
            content = f.read()

        # Accept any markdown heading level (##, ###, ####, etc.) with Self-Hosting
        self.assertRegex(
            content,
            r"#+\s+Self-Hosting",
            "README.md does not contain a 'Self-Hosting' section heading. "
            "Add a '## Self-Hosting' (or similar) section documenting that "
            "GitWeave manages its own repository via config/repos/gitweave.yaml.",
        )

    def test_readme_self_hosting_section_mentions_overlay_config(self):
        """
        The README.md Self-Hosting section must reference the overlay config file
        (config/repos/gitweave.yaml) so readers know where to find it.
        """
        with open(README_PATH) as f:
            content = f.read()

        self.assertIn(
            "gitweave.yaml",
            content,
            "README.md does not mention 'gitweave.yaml'. "
            "The Self-Hosting section must reference config/repos/gitweave.yaml "
            "so users can locate the self-hosting overlay configuration.",
        )


if __name__ == "__main__":
    unittest.main()
