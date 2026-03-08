"""
Tests for docs/getting-started.md — the onboarding guide.

These tests validate the STRUCTURE and COMPLETENESS of the guide so that a
reader following it verbatim can reach "operational" status in a fresh GitHub
org within 30 minutes.

All tests FAIL until docs/getting-started.md is written (TDD red phase).

Acceptance criteria covered:
  - File exists at docs/getting-started.md
  - Covers prerequisites (with version requirements)
  - Covers fork/template step
  - Covers GitHub App or PAT configuration
  - Covers Terraform backend setup
  - Covers applying the first overlay
  - Covers verifying metrics are flowing
  - All steps use numbered lists
  - Each major section has at least one fenced code block with a concrete command
  - A Troubleshooting section covers at least 5 distinct errors
  - README.md links to docs/getting-started.md in its first visible section
  - All files/scripts referenced in the guide actually exist in the repo
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GUIDE_PATH = os.path.join(REPO_ROOT, "docs", "getting-started.md")
README_PATH = os.path.join(REPO_ROOT, "README.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_guide() -> str:
    with open(GUIDE_PATH) as f:
        return f.read()


def _heading_positions(content: str) -> list[tuple[str, int]]:
    """
    Return list of (heading_text_lowercase, line_index) for every markdown
    heading (## level and above) in the document.
    """
    result = []
    for i, line in enumerate(content.splitlines()):
        m = re.match(r"^#{1,3}\s+(.+)", line)
        if m:
            result.append((m.group(1).lower(), i))
    return result


def _code_blocks_after_heading(content: str, heading_pattern: str) -> list[str]:
    """
    Return all fenced code-block bodies that appear after the first heading
    whose text matches `heading_pattern` (case-insensitive regex) and before
    the next same-level (or higher) heading.
    """
    lines = content.splitlines()
    heading_re = re.compile(heading_pattern, re.IGNORECASE)

    start_line = None
    start_level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,3})\s+(.+)", line)
        if m and heading_re.search(m.group(2)):
            start_line = i
            start_level = len(m.group(1))
            break

    if start_line is None:
        return []

    # Collect lines until the next heading at the same or higher level
    section_lines = []
    for line in lines[start_line + 1 :]:
        m = re.match(r"^(#{1,3})\s+", line)
        if m and len(m.group(1)) <= start_level:
            break
        section_lines.append(line)

    # Extract fenced code blocks from the collected section lines
    blocks = []
    in_block = False
    current_block: list[str] = []
    for line in section_lines:
        if line.startswith("```"):
            if in_block:
                blocks.append("\n".join(current_block))
                current_block = []
                in_block = False
            else:
                in_block = True
        elif in_block:
            current_block.append(line)
    return blocks


def _count_numbered_list_items(text: str) -> int:
    """Count markdown numbered list items (lines starting with digit + dot)."""
    return sum(1 for line in text.splitlines() if re.match(r"^\s*\d+\.\s+", line))


def _troubleshooting_error_count(content: str) -> int:
    """
    Count distinct error entries in the Troubleshooting section.
    Accepts either:
      - numbered list items  (1. Error: ...)
      - ### sub-headings     (### Error: ...)
    """
    lines = content.splitlines()
    in_trouble = False
    trouble_level: int | None = None
    count = 0

    for line in lines:
        m = re.match(r"^(#{1,4})\s+(.+)", line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).lower()
            if "troubleshoot" in heading_text:
                in_trouble = True
                trouble_level = level
                continue
            # Exit the section when we hit a heading at same or higher level
            if in_trouble and trouble_level is not None and level <= trouble_level:
                break
            # Count sub-headings within the section as error entries
            if in_trouble:
                count += 1
        elif in_trouble and re.match(r"^\s*\d+\.\s+", line):
            count += 1

    return count


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestGettingStartedGuideExists(unittest.TestCase):
    """The guide must exist at the declared path."""

    def test_guide_file_exists_at_docs_getting_started_md(self):
        """docs/getting-started.md must exist."""
        self.assertTrue(
            os.path.isfile(GUIDE_PATH),
            "docs/getting-started.md is missing — onboarding guide has not been written",
        )

    def test_guide_is_not_empty(self):
        """docs/getting-started.md must not be an empty placeholder."""
        content = _read_guide()
        self.assertGreater(
            len(content.strip()),
            200,
            "docs/getting-started.md appears to be nearly empty — minimum 200 characters required",
        )


class TestGettingStartedPrerequisites(unittest.TestCase):
    """Prerequisites section must list tools and their minimum version requirements."""

    def setUp(self):
        self.content = _read_guide()

    def test_prerequisites_section_exists(self):
        """Guide must have a Prerequisites heading."""
        headings = _heading_positions(self.content)
        self.assertTrue(
            any("prerequisite" in h for h, _ in headings),
            "docs/getting-started.md has no 'Prerequisites' section",
        )

    def test_prerequisites_mentions_git_with_version(self):
        """Prerequisites must mention git with a minimum version."""
        blocks = _code_blocks_after_heading(self.content, r"prerequisite")
        prereq_text = " ".join(blocks) + self.content

        self.assertRegex(
            prereq_text,
            r"git\s+.*\d+\.\d+",
            "Prerequisites section does not mention git with a version requirement",
        )

    def test_prerequisites_mentions_terraform_with_version(self):
        """Prerequisites must mention Terraform with a minimum version."""
        self.assertRegex(
            self.content,
            r"[Tt]erraform\s+.*\d+\.\d+",
            "Prerequisites section does not mention Terraform with a version requirement",
        )

    def test_prerequisites_mentions_github_cli_or_github_account(self):
        """Prerequisites must mention the GitHub CLI or a GitHub account requirement."""
        self.assertTrue(
            re.search(r"gh\s+cli|github cli|github account|github\.com", self.content, re.IGNORECASE),
            "Prerequisites section does not mention GitHub CLI or GitHub account requirement",
        )

    def test_prerequisites_mentions_python_with_version(self):
        """Prerequisites must mention Python (used by the metrics service) with a version."""
        self.assertRegex(
            self.content,
            r"[Pp]ython\s*\d+\.\d+|python3\s*\d+\.\d+",
            "Prerequisites section does not mention Python with a minimum version requirement",
        )


class TestGettingStartedForking(unittest.TestCase):
    """Guide must explain how to fork or use this repo as a template."""

    def setUp(self):
        self.content = _read_guide()

    def test_fork_or_template_section_exists(self):
        """Guide must have a section describing how to fork/template the control repo."""
        self.assertTrue(
            re.search(r"fork|template|clone|use this template", self.content, re.IGNORECASE),
            "docs/getting-started.md does not describe how to fork or use the repo as a template",
        )

    def test_fork_section_contains_a_command(self):
        """The fork/template step must include a concrete shell command."""
        # At least one code block must contain a git clone, gh repo fork, or template command
        all_code_blocks = re.findall(r"```(?:bash|sh)?\n(.*?)```", self.content, re.DOTALL)
        fork_commands = [
            b for b in all_code_blocks
            if re.search(r"git clone|gh repo fork|use this template|copier copy", b, re.IGNORECASE)
        ]
        self.assertGreater(
            len(fork_commands),
            0,
            "No code block with a fork/clone command found in the guide",
        )


class TestGettingStartedGitHubAppOrPAT(unittest.TestCase):
    """Guide must cover GitHub App or PAT configuration."""

    def setUp(self):
        self.content = _read_guide()

    def test_github_app_or_pat_section_exists(self):
        """Guide must have a section describing GitHub App or PAT setup."""
        self.assertTrue(
            re.search(r"github app|personal access token|PAT|GITHUB_TOKEN", self.content, re.IGNORECASE),
            "docs/getting-started.md does not cover GitHub App or PAT configuration",
        )

    def test_github_token_env_var_is_shown(self):
        """The guide must show how to set the GITHUB_TOKEN environment variable."""
        all_code_blocks = re.findall(r"```(?:bash|sh|shell)?\n(.*?)```", self.content, re.DOTALL)
        token_blocks = [
            b for b in all_code_blocks
            if "GITHUB_TOKEN" in b or "gh auth login" in b
        ]
        self.assertGreater(
            len(token_blocks),
            0,
            "No code block showing GITHUB_TOKEN or 'gh auth login' found — "
            "reader cannot know how to authenticate",
        )


class TestGettingStartedTerraformBackend(unittest.TestCase):
    """Guide must cover setting up the Terraform remote backend."""

    def setUp(self):
        self.content = _read_guide()

    def test_terraform_backend_section_exists(self):
        """Guide must have a section about configuring the Terraform backend."""
        headings = _heading_positions(self.content)
        self.assertTrue(
            any(re.search(r"terraform|backend|state", h) for h, _ in headings),
            "docs/getting-started.md has no section mentioning Terraform or the state backend",
        )

    def test_terraform_init_command_is_shown(self):
        """Guide must show the `terraform init` command."""
        all_code_blocks = re.findall(r"```(?:bash|sh|shell)?\n(.*?)```", self.content, re.DOTALL)
        init_blocks = [b for b in all_code_blocks if "terraform init" in b]
        self.assertGreater(
            len(init_blocks),
            0,
            "docs/getting-started.md has no code block containing 'terraform init'",
        )

    def test_terraform_apply_command_is_shown(self):
        """Guide must show the `terraform apply` command."""
        all_code_blocks = re.findall(r"```(?:bash|sh|shell)?\n(.*?)```", self.content, re.DOTALL)
        apply_blocks = [b for b in all_code_blocks if "terraform apply" in b]
        self.assertGreater(
            len(apply_blocks),
            0,
            "docs/getting-started.md has no code block containing 'terraform apply'",
        )


class TestGettingStartedApplyOverlay(unittest.TestCase):
    """Guide must cover applying the first overlay config."""

    def setUp(self):
        self.content = _read_guide()

    def test_overlay_section_exists(self):
        """Guide must have a section describing how to apply an overlay."""
        self.assertTrue(
            re.search(r"overlay|config/repos|gitweave-apply", self.content, re.IGNORECASE),
            "docs/getting-started.md does not describe overlay configuration",
        )

    def test_overlay_section_mentions_config_repos_directory(self):
        """Guide must reference the config/repos/ directory where overlays live."""
        self.assertIn(
            "config/repos",
            self.content,
            "docs/getting-started.md does not reference the 'config/repos/' directory",
        )

    def test_overlay_section_has_example_yaml(self):
        """Guide must include or reference an example overlay YAML."""
        self.assertTrue(
            re.search(r"example\.yaml|apiVersion.*gitweave|RepositoryOverlay", self.content, re.IGNORECASE),
            "docs/getting-started.md does not reference an example overlay YAML",
        )


class TestGettingStartedMetricsVerification(unittest.TestCase):
    """Guide must cover verifying that DORA metrics are flowing."""

    def setUp(self):
        self.content = _read_guide()

    def test_metrics_verification_section_exists(self):
        """Guide must have a section about verifying metrics."""
        self.assertTrue(
            re.search(r"metrics|/metrics|DORA|verify.*metric|metric.*flow", self.content, re.IGNORECASE),
            "docs/getting-started.md does not include a metrics verification section",
        )

    def test_metrics_endpoint_is_referenced(self):
        """Guide must reference the /metrics endpoint so the user knows what to check."""
        self.assertIn(
            "/metrics",
            self.content,
            "docs/getting-started.md does not reference the '/metrics' endpoint",
        )

    def test_webhook_setup_is_mentioned(self):
        """Guide must explain how to register the webhook so events flow to the metrics service."""
        self.assertTrue(
            re.search(r"webhook", self.content, re.IGNORECASE),
            "docs/getting-started.md does not mention webhook configuration — "
            "metrics won't flow without a registered webhook",
        )


class TestGettingStartedNumberedSteps(unittest.TestCase):
    """All major steps must use numbered lists."""

    def setUp(self):
        self.content = _read_guide()

    def test_guide_has_numbered_steps(self):
        """Guide must use numbered lists for steps (minimum 10 numbered items total)."""
        count = _count_numbered_list_items(self.content)
        self.assertGreaterEqual(
            count,
            10,
            f"docs/getting-started.md has only {count} numbered list items — "
            "guide must have at least 10 numbered steps",
        )

    def test_each_major_section_has_at_least_one_code_block(self):
        """
        The guide must have concrete commands — not just prose — so the user
        can copy-paste without interpretation.  At minimum, 5 fenced code
        blocks must exist.
        """
        code_blocks = re.findall(r"```", self.content)
        # Each block uses two fences (open + close)
        num_blocks = len(code_blocks) // 2
        self.assertGreaterEqual(
            num_blocks,
            5,
            f"docs/getting-started.md has only {num_blocks} code block(s) — "
            "at least 5 are required so every major step has a concrete command",
        )


class TestGettingStartedTroubleshooting(unittest.TestCase):
    """Troubleshooting section must cover the top 5 errors."""

    def setUp(self):
        self.content = _read_guide()

    def test_troubleshooting_section_exists(self):
        """Guide must have a 'Troubleshooting' section."""
        headings = _heading_positions(self.content)
        self.assertTrue(
            any("troubleshoot" in h for h, _ in headings),
            "docs/getting-started.md has no 'Troubleshooting' section",
        )

    def test_troubleshooting_covers_at_least_five_errors(self):
        """
        Troubleshooting section must document at least 5 distinct errors or
        failure modes (as numbered items or sub-headings).
        """
        count = _troubleshooting_error_count(self.content)
        self.assertGreaterEqual(
            count,
            5,
            f"Troubleshooting section documents only {count} error(s) — "
            "acceptance criteria requires at least 5",
        )


class TestGettingStartedReferencedFilesExist(unittest.TestCase):
    """
    Every script or config file that the guide tells the user to run or edit
    must actually exist in the repo.
    """

    def setUp(self):
        self.content = _read_guide()

    def _all_code_block_commands(self) -> list[str]:
        return re.findall(r"```(?:bash|sh|shell)?\n(.*?)```", self.content, re.DOTALL)

    def test_bootstrap_sh_exists_if_referenced(self):
        """If guide references scripts/bootstrap.sh, that file must exist."""
        if "bootstrap.sh" not in self.content:
            self.skipTest("bootstrap.sh not referenced in the guide")
        self.assertTrue(
            os.path.isfile(os.path.join(REPO_ROOT, "scripts", "bootstrap.sh")),
            "Guide references scripts/bootstrap.sh but the file does not exist",
        )

    def test_infra_directory_exists_if_referenced(self):
        """If guide references the infra/ directory, it must exist."""
        if "infra/" not in self.content and "cd infra" not in self.content:
            self.skipTest("infra/ not referenced in the guide")
        self.assertTrue(
            os.path.isdir(os.path.join(REPO_ROOT, "infra")),
            "Guide references the infra/ directory but it does not exist",
        )

    def test_config_repos_directory_exists_if_referenced(self):
        """If guide references config/repos/, that directory must exist."""
        if "config/repos" not in self.content:
            self.skipTest("config/repos not referenced in the guide")
        self.assertTrue(
            os.path.isdir(os.path.join(REPO_ROOT, "config", "repos")),
            "Guide references config/repos/ but that directory does not exist",
        )

    def test_metrics_dockerfile_exists_if_referenced(self):
        """If guide references the metrics Dockerfile, it must exist."""
        if not re.search(r"[Dd]ockerfile|docker build|docker run", self.content):
            self.skipTest("Docker not referenced in the guide")
        self.assertTrue(
            os.path.isfile(os.path.join(REPO_ROOT, "metrics", "Dockerfile")),
            "Guide references Docker for the metrics service but metrics/Dockerfile does not exist",
        )


class TestReadmeLinksToGuide(unittest.TestCase):
    """README.md must link to docs/getting-started.md in its first section."""

    def setUp(self):
        with open(README_PATH) as f:
            self.readme = f.read()

    def test_readme_contains_link_to_getting_started(self):
        """README.md must contain a markdown link to docs/getting-started.md."""
        self.assertTrue(
            re.search(r"\[.*?\]\(.*?docs/getting-started\.md.*?\)", self.readme),
            "README.md does not contain a link to docs/getting-started.md",
        )

    def test_readme_link_is_in_first_section(self):
        """
        The link to docs/getting-started.md must appear in the first 60 lines
        of README.md so it is prominent for new users.
        """
        first_section = "\n".join(self.readme.splitlines()[:60])
        self.assertTrue(
            re.search(r"getting-started", first_section, re.IGNORECASE),
            "README.md does not link to docs/getting-started.md in its first 60 lines — "
            "the link must be prominent for new users",
        )

    def test_readme_link_text_is_descriptive(self):
        """
        The link text must be descriptive (e.g. 'Getting Started' or 'Quick Start')
        rather than a bare URL.
        """
        self.assertTrue(
            re.search(
                r"\[(Getting Started|Quick Start|Get Started|getting-started)[^\]]*\]"
                r"\(.*?getting-started.*?\)",
                self.readme,
                re.IGNORECASE,
            ),
            "README.md link to the guide must use descriptive text like 'Getting Started'",
        )


if __name__ == "__main__":
    unittest.main()
