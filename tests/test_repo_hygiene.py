"""Repository hygiene checks — WI-4."""
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_claude_md_is_one_liner():
    """CLAUDE.md must contain exactly one line: 'See AGENTS.md.'"""
    claude_md = REPO_ROOT / "CLAUDE.md"
    assert claude_md.exists(), "CLAUDE.md must exist"
    content = claude_md.read_text()
    lines = [l for l in content.splitlines() if l.strip()]
    assert lines == ["See AGENTS.md."], (
        f"CLAUDE.md must contain exactly one non-empty line 'See AGENTS.md.' "
        f"but got: {lines!r}"
    )


def _gitignore_patterns():
    gitignore = REPO_ROOT / ".gitignore"
    assert gitignore.exists(), ".gitignore must exist"
    return gitignore.read_text().splitlines()


def test_gitignore_covers_secrets_env():
    assert "secrets.env" in _gitignore_patterns(), \
        ".gitignore must include 'secrets.env'"


def test_gitignore_covers_pytest_cache():
    assert ".pytest_cache/" in _gitignore_patterns(), \
        ".gitignore must include '.pytest_cache/'"


def test_gitignore_covers_preflight_md():
    assert "_preflight*.md" in _gitignore_patterns(), \
        ".gitignore must include '_preflight*.md'"
