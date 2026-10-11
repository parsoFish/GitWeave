"""
WI-14: Verify no Terraform tokens remain in docs, README or copilot-context.

AC1: GIVEN the repository after I2 (infra/ removed)
     WHEN this suite runs
     THEN no file under docs/ and neither .github/copilot-context.md nor README.md
          contains the tokens 'terraform', 'infra/' or 'TF_' (case-insensitive).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

BANNED_PATTERNS = [
    re.compile(r"terraform", re.IGNORECASE),
    re.compile(r"infra/", re.IGNORECASE),
    re.compile(r"TF_", re.IGNORECASE),
]

EXPLICIT_FILES = [
    ROOT / ".github" / "copilot-context.md",
    ROOT / "README.md",
]

DOCS_DIR = ROOT / "docs"


def _collect_docs_files():
    if DOCS_DIR.exists():
        return list(DOCS_DIR.rglob("*.md")) + list(DOCS_DIR.rglob("*.txt"))
    return []


def _check_file(path: Path):
    text = path.read_text(encoding="utf-8")
    hits = []
    for pattern in BANNED_PATTERNS:
        found = pattern.findall(text)
        if found:
            hits.append((pattern.pattern, found[:5]))
    return hits


class TestNoTerraformTokensInDocs:
    def test_readme_no_terraform_tokens(self):
        """README.md must not contain terraform, infra/ or TF_."""
        path = ROOT / "README.md"
        hits = _check_file(path)
        assert hits == [], (
            f"README.md still contains banned tokens: {hits}"
        )

    def test_copilot_context_no_terraform_tokens(self):
        """.github/copilot-context.md must not contain terraform, infra/ or TF_."""
        path = ROOT / ".github" / "copilot-context.md"
        hits = _check_file(path)
        assert hits == [], (
            f".github/copilot-context.md still contains banned tokens: {hits}"
        )

    def test_docs_files_no_terraform_tokens(self):
        """No file under docs/ must contain terraform, infra/ or TF_."""
        docs_files = _collect_docs_files()
        failures = {}
        for path in docs_files:
            hits = _check_file(path)
            if hits:
                failures[str(path.relative_to(ROOT))] = hits
        assert failures == {}, (
            f"docs/ files still contain banned tokens:\n"
            + "\n".join(f"  {k}: {v}" for k, v in failures.items())
        )
