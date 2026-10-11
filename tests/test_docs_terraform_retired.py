"""
WI-11: Verify Terraform references are removed from docs and gw usage is documented.

AC1: README.md and docs/demo-guide.md contain no 'terraform' references (case-insensitive)
AC2: README.md contains no 'infra/' references
AC3: README.md contains 'gw plan'
AC4: docs/demo-guide.md contains 'gw apply'
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
DEMO_GUIDE = ROOT / "docs" / "demo-guide.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestTerraformRetiredFromDocs:
    def test_readme_no_terraform(self):
        """AC1: README.md has no Terraform references."""
        text = _text(README)
        matches = re.findall(r"terraform", text, re.IGNORECASE)
        assert matches == [], (
            f"README.md still contains {len(matches)} Terraform reference(s): "
            f"{matches[:5]}"
        )

    def test_demo_guide_no_terraform(self):
        """AC1: docs/demo-guide.md has no Terraform references."""
        text = _text(DEMO_GUIDE)
        matches = re.findall(r"terraform", text, re.IGNORECASE)
        assert matches == [], (
            f"docs/demo-guide.md still contains {len(matches)} Terraform reference(s): "
            f"{matches[:5]}"
        )

    def test_readme_no_infra_dir(self):
        """AC2: README.md has no infra/ directory references."""
        text = _text(README)
        matches = re.findall(r"infra/", text)
        assert matches == [], (
            f"README.md still contains {len(matches)} 'infra/' reference(s): "
            f"{matches[:5]}"
        )

    def test_readme_has_gw_plan(self):
        """AC3: README.md documents gw plan usage."""
        text = _text(README)
        assert "gw plan" in text, "README.md must contain 'gw plan' usage"

    def test_demo_guide_has_gw_apply(self):
        """AC4: docs/demo-guide.md documents gw apply usage."""
        text = _text(DEMO_GUIDE)
        assert "gw apply" in text, "docs/demo-guide.md must contain 'gw apply' usage"
