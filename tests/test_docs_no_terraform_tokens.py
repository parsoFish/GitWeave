"""
WI-14/WI-15: Verify no Terraform tokens remain in docs, README or copilot-context.

AC1 (WI-14): GIVEN the repository after I2 (infra/ removed)
     WHEN this suite runs
     THEN no file under docs/ and neither .github/copilot-context.md nor README.md
          contains the tokens 'terraform', 'infra/' or 'TF_' (case-insensitive).

K3b (WI-15): Guard scans GitWeave docs only (never modules/):
     - test_bite_*: planted token in a tmp copy of docs/ is flagged.
     - test_modules_*: planted token under modules/ is ignored.
"""

import re
import shutil
import tempfile
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


def _collect_docs_files(root: Path = ROOT):
    docs_dir = root / "docs"
    if docs_dir.exists():
        return list(docs_dir.rglob("*.md")) + list(docs_dir.rglob("*.txt"))
    return []


def _collect_explicit_files(root: Path = ROOT):
    return [
        root / ".github" / "copilot-context.md",
        root / "README.md",
    ]


def _check_file(path: Path):
    text = path.read_text(encoding="utf-8")
    hits = []
    for pattern in BANNED_PATTERNS:
        found = pattern.findall(text)
        if found:
            hits.append((pattern.pattern, found[:5]))
    return hits


def _scan_tree(root: Path):
    """Scan docs + explicit files under root; return {rel_path: hits} for failures."""
    failures = {}
    for path in _collect_explicit_files(root):
        if path.exists():
            hits = _check_file(path)
            if hits:
                failures[str(path.relative_to(root))] = hits
    for path in _collect_docs_files(root):
        hits = _check_file(path)
        if hits:
            failures[str(path.relative_to(root))] = hits
    return failures


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


class TestGuardNarrowingK3b:
    """K3b: guard scans docs only, not modules/."""

    def test_bite_planted_terraform_token_in_docs_is_flagged(self):
        """Guard flags a planted Terraform token inside a temporary docs/ copy."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            tmp_docs = tmp_root / "docs"
            tmp_docs.mkdir()
            poison = tmp_docs / "planted.md"
            poison.write_text("terraform init\n", encoding="utf-8")
            failures = _scan_tree(tmp_root)
            assert failures, (
                "Guard should have flagged 'terraform' in docs/planted.md but found nothing."
            )

    def test_modules_planted_terraform_token_is_ignored(self):
        """Guard does NOT flag a Terraform token planted under modules/."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            modules_dir = tmp_root / "modules" / "terraform_module"
            modules_dir.mkdir(parents=True)
            (modules_dir / "main.tf").write_text(
                "terraform { required_version = \">= 1.5.0\" }\n",
                encoding="utf-8",
            )
            failures = _scan_tree(tmp_root)
            assert failures == {}, (
                f"Guard must not scan modules/; got failures: {failures}"
            )
