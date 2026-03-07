"""
Tests for docs/module-authoring.md — the developer guide for creating new GitWeave modules.

These tests verify that the guide:
  - Exists at docs/module-authoring.md
  - Covers all mandatory topics with concrete examples:
      - Module directory structure (modules/<name>/ layout)
      - copier.yaml required and optional fields (reference table)
      - Jinja2 templating syntax and best practices
      - Variable types and validation
      - Module composition and inheritance
      - Local testing workflow (copier copy command)
      - CalVer versioning convention (YYYYMMDD.Patch)
      - Publishing a module update
      - Conflict resolution runbook for copier update 3-way merge scenarios
  - Contains a numbered "Your First Module" walkthrough section
  - Includes a copier.yaml reference table with type, required/optional, and example columns
  - Documents the canonical local testing command:
      copier copy modules/<name> /tmp/test-output
  - Contains a conflict resolution runbook for copier update merge conflicts
  - All shell command examples use valid copier CLI syntax
  - README.md has a link to docs/module-authoring.md

All tests in this file will fail until docs/module-authoring.md is authored
(TDD red phase). README tests will also fail until the link is added.
"""

import os
import re
import subprocess
import unittest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GUIDE_PATH = os.path.join(REPO_ROOT, "docs", "module-authoring.md")
README_PATH = os.path.join(REPO_ROOT, "README.md")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _read_guide() -> str:
    """Read docs/module-authoring.md as a string. Raises if the file is absent."""
    if not os.path.isfile(GUIDE_PATH):
        raise FileNotFoundError(
            f"docs/module-authoring.md not found at {GUIDE_PATH} — "
            "the guide must be authored before these tests can pass"
        )
    with open(GUIDE_PATH, encoding="utf-8") as f:
        return f.read()


def _read_readme() -> str:
    with open(README_PATH, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# TestGuideExists
# ---------------------------------------------------------------------------


class TestGuideExists(unittest.TestCase):
    """Sanity checks that the guide file is present and non-empty."""

    def test_docs_directory_exists(self):
        """docs/ directory must exist at repo root."""
        docs_dir = os.path.join(REPO_ROOT, "docs")
        self.assertTrue(
            os.path.isdir(docs_dir),
            "docs/ directory is missing from the repo root",
        )

    def test_module_authoring_md_exists(self):
        """docs/module-authoring.md must exist at the canonical path."""
        self.assertTrue(
            os.path.isfile(GUIDE_PATH),
            f"docs/module-authoring.md not found at {GUIDE_PATH}",
        )

    def test_guide_is_not_empty(self):
        """docs/module-authoring.md must have meaningful content (> 500 characters)."""
        content = _read_guide()
        self.assertGreater(
            len(content),
            500,
            "docs/module-authoring.md appears to be a stub — it has fewer than 500 characters",
        )


# ---------------------------------------------------------------------------
# TestGuideSections — all mandatory topics must be present
# ---------------------------------------------------------------------------


class TestGuideSections(unittest.TestCase):
    """Each mandatory topic must appear as a heading or named section in the guide."""

    def _assert_section_present(self, pattern: str, description: str):
        content = _read_guide()
        self.assertTrue(
            re.search(pattern, content, re.IGNORECASE | re.MULTILINE),
            f"docs/module-authoring.md is missing a section on: {description}\n"
            f"Expected to find a pattern matching: {pattern!r}",
        )

    def test_section_directory_structure(self):
        """Guide must cover module directory structure."""
        self._assert_section_present(
            r"#+ .*directory structure",
            "Module directory structure",
        )

    def test_section_copier_yaml_fields(self):
        """Guide must cover copier.yaml required and optional fields."""
        self._assert_section_present(
            r"#+ .*copier\.yaml",
            "copier.yaml fields reference",
        )

    def test_section_jinja2_templating(self):
        """Guide must cover Jinja2 templating syntax and best practices."""
        self._assert_section_present(
            r"#+ .*jinja2|#+ .*templating",
            "Jinja2 templating syntax",
        )

    def test_section_variable_types_and_validation(self):
        """Guide must cover variable types and validation."""
        self._assert_section_present(
            r"#+ .*variable|#+ .*validation",
            "Variable types and validation",
        )

    def test_section_composition_and_inheritance(self):
        """Guide must cover module composition and inheritance."""
        self._assert_section_present(
            r"#+ .*composition|#+ .*inherit",
            "Module composition and inheritance",
        )

    def test_section_local_testing(self):
        """Guide must cover the local testing workflow."""
        self._assert_section_present(
            r"#+ .*local test|#+ .*testing",
            "Local testing workflow",
        )

    def test_section_calver_versioning(self):
        """Guide must cover CalVer versioning convention."""
        self._assert_section_present(
            r"#+ .*calver|#+ .*version",
            "CalVer versioning convention",
        )

    def test_section_publishing(self):
        """Guide must cover how to publish a module update."""
        self._assert_section_present(
            r"#+ .*publish|#+ .*releasing|#+ .*release",
            "Publishing / releasing a module update",
        )

    def test_section_conflict_resolution(self):
        """Guide must cover the conflict resolution runbook."""
        self._assert_section_present(
            r"#+ .*conflict",
            "Conflict resolution runbook",
        )


# ---------------------------------------------------------------------------
# TestYourFirstModuleWalkthrough
# ---------------------------------------------------------------------------


class TestYourFirstModuleWalkthrough(unittest.TestCase):
    """'Your First Module' must be a numbered walkthrough section."""

    def test_your_first_module_heading_exists(self):
        """Guide must contain a 'Your First Module' section heading."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"#+ .*your first module", content, re.IGNORECASE),
            "docs/module-authoring.md is missing a 'Your First Module' section heading",
        )

    def test_your_first_module_is_numbered_steps(self):
        """'Your First Module' section must contain at least 3 numbered steps."""
        content = _read_guide()
        # Find the section
        match = re.search(
            r"#+ .*your first module.*?(?=\n#|\Z)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "Could not locate the 'Your First Module' section body",
        )
        section_text = match.group(0)
        # Count lines starting with a number followed by a period (e.g., "1.", "2.")
        numbered_steps = re.findall(r"^\s*\d+\.", section_text, re.MULTILINE)
        self.assertGreaterEqual(
            len(numbered_steps),
            3,
            f"'Your First Module' walkthrough must have at least 3 numbered steps; "
            f"found {len(numbered_steps)}",
        )

    def test_your_first_module_produces_working_module(self):
        """The walkthrough must include a copier copy or copier run command example."""
        content = _read_guide()
        match = re.search(
            r"#+ .*your first module.*?(?=\n#|\Z)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not locate the 'Your First Module' section body")
        section_text = match.group(0)
        self.assertTrue(
            re.search(r"copier\s+(copy|run)", section_text, re.IGNORECASE),
            "The 'Your First Module' section must include a 'copier copy' or 'copier run' "
            "command to show the reader how to test the module they create",
        )


# ---------------------------------------------------------------------------
# TestCopierYamlReferenceTable
# ---------------------------------------------------------------------------


class TestCopierYamlReferenceTable(unittest.TestCase):
    """copier.yaml reference table must cover fields with type, required/optional, and examples."""

    def test_reference_table_has_required_column(self):
        """Reference table must label fields as Required or Optional."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"required|optional", content, re.IGNORECASE),
            "docs/module-authoring.md must mark copier.yaml fields as Required or Optional",
        )

    def test_reference_table_has_type_column(self):
        """Reference table must document the type of each field."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"\btype\b", content, re.IGNORECASE),
            "docs/module-authoring.md must include a 'Type' column in the copier.yaml reference",
        )

    def test_reference_table_covers_metadata_name(self):
        """Reference table must document the _metadata.name field."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"_metadata\.name|`name`", content, re.IGNORECASE),
            "copier.yaml reference must document the _metadata.name field",
        )

    def test_reference_table_covers_metadata_version(self):
        """Reference table must document the _metadata.version field."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"_metadata\.version|`version`", content, re.IGNORECASE),
            "copier.yaml reference must document the _metadata.version field",
        )

    def test_reference_table_covers_metadata_description(self):
        """Reference table must document the _metadata.description field."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"_metadata\.description|`description`", content, re.IGNORECASE),
            "copier.yaml reference must document the _metadata.description field",
        )

    def test_reference_table_has_example_values(self):
        """Reference table must include at least one concrete example value."""
        content = _read_guide()
        # An example value is typically shown in backticks or a table cell.
        # Look for a CalVer example (the canonical version format) or a snake_case name.
        self.assertTrue(
            re.search(r"2024\d{4}\.\d|example_module|my_module", content, re.IGNORECASE),
            "copier.yaml reference table must include concrete example values "
            "(e.g. a CalVer version like '20240101.0' or a module name like 'example_module')",
        )


# ---------------------------------------------------------------------------
# TestLocalTestingInstructions
# ---------------------------------------------------------------------------


class TestLocalTestingInstructions(unittest.TestCase):
    """Local testing section must document the canonical copier copy command."""

    def test_copier_copy_command_present(self):
        """Guide must include a 'copier copy' command for local testing."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"copier\s+copy", content, re.IGNORECASE),
            "docs/module-authoring.md must include a 'copier copy' command",
        )

    def test_copier_copy_references_modules_path(self):
        """The copier copy example must reference the modules/ directory."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"copier\s+copy\s+modules/", content, re.IGNORECASE),
            "The 'copier copy' example must reference 'modules/<name>' as the source path",
        )

    def test_copier_copy_references_tmp_test_output(self):
        """The copier copy example must use /tmp/test-output as the destination."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"copier\s+copy\s+modules/\S+\s+/tmp/test-output", content, re.IGNORECASE),
            "Local testing instructions must show: copier copy modules/<name> /tmp/test-output",
        )

    def test_local_testing_mentions_cleanup(self):
        """Local testing section should mention cleaning up /tmp/test-output between runs."""
        content = _read_guide()
        # Look for rm -rf /tmp/test-output or equivalent
        self.assertTrue(
            re.search(r"rm\s+-rf\s+/tmp/test-output|clean up|cleanup", content, re.IGNORECASE),
            "Local testing section should document how to clean up the test output directory "
            "between runs to avoid stale state",
        )


# ---------------------------------------------------------------------------
# TestCalVerVersioningConvention
# ---------------------------------------------------------------------------


class TestCalVerVersioningConvention(unittest.TestCase):
    """CalVer section must explain the YYYYMMDD.Patch format and its usage."""

    def test_calver_format_documented(self):
        """Guide must show or describe the YYYYMMDD.Patch CalVer pattern."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"YYYYMMDD\.Patch|YYYYMMDD\.\d|calver.*YYYYMMDD", content, re.IGNORECASE),
            "Guide must document the CalVer format: YYYYMMDD.Patch",
        )

    def test_calver_concrete_example_present(self):
        """Guide must include a concrete CalVer version string as an example."""
        content = _read_guide()
        # Match a real CalVer string like 20240101.0 or 20251231.3
        self.assertTrue(
            re.search(r"\b20\d{6}\.\d+\b", content),
            "Guide must include a concrete CalVer example (e.g. '20240101.0')",
        )

    def test_calver_explains_patch_increment(self):
        """Guide must explain when to increment the Patch component."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"patch.*increment|increment.*patch|same day", content, re.IGNORECASE),
            "Guide must explain when the Patch number increments (e.g. multiple releases on the same day)",
        )


# ---------------------------------------------------------------------------
# TestConflictResolutionRunbook
# ---------------------------------------------------------------------------


class TestConflictResolutionRunbook(unittest.TestCase):
    """Conflict resolution section must document 3-way merge scenarios for copier update."""

    def test_conflict_section_covers_copier_update(self):
        """Runbook must mention 'copier update' (the command that triggers conflicts)."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"copier\s+update", content, re.IGNORECASE),
            "Conflict resolution runbook must reference 'copier update'",
        )

    def test_conflict_section_describes_three_way_merge(self):
        """Runbook must explain 3-way merge or conflict markers."""
        content = _read_guide()
        self.assertTrue(
            re.search(
                r"3-way merge|three-way merge|conflict marker|<<<<<<|HEAD",
                content,
                re.IGNORECASE,
            ),
            "Conflict resolution runbook must describe 3-way merge scenarios or conflict markers",
        )

    def test_conflict_section_provides_resolution_steps(self):
        """Runbook must provide numbered or bulleted steps to resolve conflicts."""
        content = _read_guide()
        # Find the conflict section
        match = re.search(
            r"#+ .*conflict.*?(?=\n#|\Z)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(match, "Could not locate the conflict resolution section body")
        section_text = match.group(0)
        # Must contain at least 2 actionable steps (numbered or bulleted)
        steps = re.findall(r"^\s*(\d+\.|[-*])\s+\S", section_text, re.MULTILINE)
        self.assertGreaterEqual(
            len(steps),
            2,
            f"Conflict resolution runbook must have at least 2 steps; found {len(steps)}",
        )

    def test_conflict_section_mentions_git_merge_or_diff(self):
        """Runbook must reference git operations used during conflict resolution."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"git\s+(merge|diff|add|checkout|status)", content, re.IGNORECASE),
            "Conflict resolution runbook must reference relevant git commands "
            "(e.g. git diff, git add, git merge)",
        )

    def test_conflict_section_covers_copier_answers_file(self):
        """Runbook must mention .copier-answers.yml (the file that tracks applied version)."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"\.copier-answers\.(yml|yaml)", content, re.IGNORECASE),
            "Conflict resolution runbook must mention .copier-answers.yml "
            "as it tracks which version was applied",
        )


# ---------------------------------------------------------------------------
# TestCompositionAndInheritance
# ---------------------------------------------------------------------------


class TestCompositionAndInheritance(unittest.TestCase):
    """Composition section must explain how to apply multiple modules to one repo."""

    def test_composition_mentions_multiple_modules(self):
        """Composition section must explain applying multiple modules."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"multiple modules|composing modules|apply.*module", content, re.IGNORECASE),
            "Composition section must explain applying multiple modules to a single repository",
        )

    def test_composition_covers_overlay_config(self):
        """Composition section must reference overlay config or config/repos/."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"overlay|config/repos|spec\.modules", content, re.IGNORECASE),
            "Composition section must reference overlay config (config/repos/) "
            "where module lists are defined",
        )


# ---------------------------------------------------------------------------
# TestJinja2BestPractices
# ---------------------------------------------------------------------------


class TestJinja2BestPractices(unittest.TestCase):
    """Jinja2 section must include syntax examples and best-practice guidance."""

    def test_jinja2_variable_syntax_shown(self):
        """Guide must show the {{ variable }} Jinja2 variable syntax."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"\{\{.*?\}\}", content),
            "Guide must include a Jinja2 {{ variable }} syntax example",
        )

    def test_jinja2_control_flow_shown(self):
        """Guide must show Jinja2 block syntax ({% %}) for control flow."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"\{%.*?%\}", content),
            "Guide must include Jinja2 {% %} block syntax for control flow (if/for)",
        )

    def test_jinja2_strict_undefined_mentioned(self):
        """Guide must mention StrictUndefined or undefined variable handling."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"StrictUndefined|undefined variable|strict.*undefined", content, re.IGNORECASE),
            "Guide must advise on undefined variable handling (StrictUndefined) "
            "to catch typos early",
        )


# ---------------------------------------------------------------------------
# TestPublishingWorkflow
# ---------------------------------------------------------------------------


class TestPublishingWorkflow(unittest.TestCase):
    """Publishing section must describe the steps to release a module update."""

    def test_publishing_mentions_git_tag(self):
        """Publishing section must mention git tagging."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"git tag|git push.*tags|v\d{4}", content, re.IGNORECASE),
            "Publishing section must describe creating a git tag for the module release",
        )

    def test_publishing_mentions_calver_tag_format(self):
        """Publishing section must show the CalVer tag format (vYYYYMMDD.Patch)."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"v20\d{6}\.\d+|vYYYYMMDD", content, re.IGNORECASE),
            "Publishing section must show the CalVer git tag format (e.g. v20240101.0)",
        )

    def test_publishing_mentions_pr_propagation(self):
        """Publishing section must explain that a tag triggers PR propagation to consumers."""
        content = _read_guide()
        self.assertTrue(
            re.search(
                r"pull request|gitweave-apply|propagat|consumer",
                content,
                re.IGNORECASE,
            ),
            "Publishing section must explain that pushing a tag triggers PR propagation "
            "to consuming repositories via gitweave-apply",
        )


# ---------------------------------------------------------------------------
# TestReadmeLinksToGuide
# ---------------------------------------------------------------------------


class TestReadmeLinksToGuide(unittest.TestCase):
    """README.md must contain a Markdown link to docs/module-authoring.md."""

    def test_readme_links_to_module_authoring_guide(self):
        """README.md must have a link pointing to docs/module-authoring.md."""
        content = _read_readme()
        self.assertTrue(
            re.search(r"docs/module-authoring\.md", content),
            "README.md must link to docs/module-authoring.md "
            "(e.g. [Module Authoring Guide](docs/module-authoring.md))",
        )

    def test_readme_link_is_a_markdown_hyperlink(self):
        """The docs/module-authoring.md reference in README.md must be a Markdown hyperlink."""
        content = _read_readme()
        self.assertTrue(
            re.search(r"\[.+?\]\(docs/module-authoring\.md\)", content),
            "README.md must include a Markdown hyperlink: [label](docs/module-authoring.md)",
        )


# ---------------------------------------------------------------------------
# TestCommandExamplesSyntax
# ---------------------------------------------------------------------------


class TestCommandExamplesSyntax(unittest.TestCase):
    """Shell command examples extracted from the guide must use valid copier CLI syntax."""

    def _extract_code_block_commands(self, content: str):
        """Extract lines starting with 'copier' from fenced code blocks in the guide."""
        # Match fenced code blocks (``` or ```bash or ```sh)
        code_blocks = re.findall(r"```[a-z]*\n(.*?)```", content, re.DOTALL)
        commands = []
        for block in code_blocks:
            for line in block.splitlines():
                stripped = line.strip()
                if stripped.startswith("copier"):
                    commands.append(stripped)
        return commands

    def test_at_least_two_copier_commands_documented(self):
        """Guide must include at least two distinct copier command examples."""
        content = _read_guide()
        commands = self._extract_code_block_commands(content)
        self.assertGreaterEqual(
            len(commands),
            2,
            f"Guide must show at least 2 copier command examples in code blocks; "
            f"found {len(commands)}: {commands}",
        )

    def test_copier_copy_command_has_two_positional_args(self):
        """'copier copy' examples must specify both a source and a destination."""
        content = _read_guide()
        commands = self._extract_code_block_commands(content)
        copy_commands = [c for c in commands if re.match(r"copier\s+copy\b", c)]
        self.assertTrue(
            copy_commands,
            "Guide must have at least one 'copier copy' command in a code block",
        )
        for cmd in copy_commands:
            # After "copier copy" there should be at least two non-flag tokens
            parts = cmd.split()
            non_flag_parts = [p for p in parts[2:] if not p.startswith("-")]
            self.assertGreaterEqual(
                len(non_flag_parts),
                2,
                f"'copier copy' command must have a source and destination: {cmd!r}",
            )

    @unittest.skipUnless(
        subprocess.run(["which", "copier"], capture_output=True).returncode == 0,
        "copier binary not found — skipping live CLI syntax check",
    )
    def test_copier_help_succeeds(self):
        """copier --help exits 0, confirming the CLI is available for testing."""
        result = subprocess.run(
            ["copier", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"copier --help failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
        )


# ---------------------------------------------------------------------------
# TestModuleDirectoryStructure
# ---------------------------------------------------------------------------


class TestModuleDirectoryStructure(unittest.TestCase):
    """Module directory structure section must document the expected layout."""

    def test_structure_shows_copier_yaml_file(self):
        """Structure section must show copier.yaml as part of the module layout."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"copier\.yaml", content),
            "Directory structure section must show copier.yaml as part of the module",
        )

    def test_structure_shows_modules_subdirectory(self):
        """Structure section must show that modules live under modules/<name>/."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"modules/<name>|modules/my_module|modules/\w", content, re.IGNORECASE),
            "Directory structure section must show the modules/<name>/ path convention",
        )

    def test_structure_shows_template_content_location(self):
        """Structure section must show where template files (content/) are placed."""
        content = _read_guide()
        self.assertTrue(
            re.search(r"content/|template files|\.jinja", content, re.IGNORECASE),
            "Directory structure section must show where Jinja2 template files are placed "
            "(e.g. a content/ subdirectory or .jinja file extensions)",
        )


if __name__ == "__main__":
    unittest.main()
