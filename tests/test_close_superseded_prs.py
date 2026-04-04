"""
Tests verifying that PRs #22, #23, and #24 have been closed as superseded by #21.

PRs under test:
  - #22  docs: Add metrics service deployment guide for K8s, ECS, and Cloud Run
  - #23  feat: Persistent DORA metrics with PostgreSQL event store and integration tests
  - #24  feat: implement getting-started guide, PostgreSQL metrics persistence, and architecture specs

Acceptance criteria:
  - Each PR is in the "CLOSED" state (not merged, not open)
  - Each PR has at least one comment that:
      * References PR #21 as the superseding PR
      * Notes which unique content will be reintroduced in a future milestone

All tests in this file FAIL until the three PRs are closed with the correct rationale
comment (TDD red phase).
"""

import subprocess
import unittest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPERSEDED_PR_NUMBERS = [22, 23, 24]
SUPERSEDING_PR_NUMBER = 21

# Keywords that must appear in the supersedence comment (case-insensitive).
# We look for "#21" (or "21") and words conveying supersedence / future work.
SUPERSEDENCE_KEYWORDS = ["#21", "supersed"]
FUTURE_MILESTONE_KEYWORDS = ["future", "milestone", "reintroduce", "upcoming", "later"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gh(*args: str) -> subprocess.CompletedProcess:
    """Run a `gh` CLI command and return the completed process."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
    )


def _pr_state(pr_number: int) -> str:
    """Return the state of a PR as a string: OPEN, CLOSED, or MERGED."""
    result = _gh(
        "pr", "view", str(pr_number),
        "--json", "state",
        "--jq", ".state",
    )
    if result.returncode != 0:
        return "UNKNOWN"
    return result.stdout.strip().upper()


def _pr_comments(pr_number: int) -> list[str]:
    """
    Return a list of comment bodies for the given PR.
    Includes both the PR body and all review/issue comments.
    """
    result = _gh(
        "pr", "view", str(pr_number),
        "--json", "comments",
        "--jq", "[.comments[].body]",
    )
    if result.returncode != 0:
        return []
    import json
    try:
        return json.loads(result.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return []


def _has_supersedence_comment(pr_number: int) -> tuple[bool, str]:
    """
    Return (True, "") if a comment on the PR references #21 as superseding it
    and mentions future milestone reintroduction; otherwise (False, reason).
    """
    comments = _pr_comments(pr_number)
    if not comments:
        return False, f"PR #{pr_number} has no comments"

    for body in comments:
        lower = body.lower()
        has_pr21_ref = any(kw.lower() in lower for kw in SUPERSEDENCE_KEYWORDS)
        has_future_ref = any(kw.lower() in lower for kw in FUTURE_MILESTONE_KEYWORDS)
        if has_pr21_ref and has_future_ref:
            return True, ""

    return (
        False,
        f"PR #{pr_number} has no comment that both references #21 and mentions "
        f"future milestone reintroduction. "
        f"Comments found: {[c[:120] for c in comments]}",
    )


# ---------------------------------------------------------------------------
# Tests — PR closed state
# ---------------------------------------------------------------------------


class TestSupersededPRsClosed(unittest.TestCase):
    """Verify that each superseded PR is in CLOSED state (not open, not merged)."""

    def test_pr_22_is_closed(self):
        """PR #22 (deployment guide) must be closed, not open or merged."""
        state = _pr_state(22)
        self.assertEqual(
            state,
            "CLOSED",
            f"PR #22 is in state '{state}' — expected CLOSED. "
            "Close it (do not merge) with `gh pr close 22`.",
        )

    def test_pr_23_is_closed(self):
        """PR #23 (integration tests / PostgreSQL event store) must be closed."""
        state = _pr_state(23)
        self.assertEqual(
            state,
            "CLOSED",
            f"PR #23 is in state '{state}' — expected CLOSED. "
            "Close it (do not merge) with `gh pr close 23`.",
        )

    def test_pr_24_is_closed(self):
        """PR #24 (getting-started guide / architecture specs) must be closed."""
        state = _pr_state(24)
        self.assertEqual(
            state,
            "CLOSED",
            f"PR #24 is in state '{state}' — expected CLOSED. "
            "Close it (do not merge) with `gh pr close 24`.",
        )

    def test_all_superseded_prs_are_closed(self):
        """All three superseded PRs must be closed simultaneously."""
        not_closed = {
            n: _pr_state(n)
            for n in SUPERSEDED_PR_NUMBERS
            if _pr_state(n) != "CLOSED"
        }
        self.assertEqual(
            not_closed,
            {},
            f"The following PRs are not yet closed: {not_closed}",
        )


# ---------------------------------------------------------------------------
# Tests — supersedence comment present
# ---------------------------------------------------------------------------


class TestSupersededPRsHaveRationaleComment(unittest.TestCase):
    """
    Verify that each closed PR has a comment explaining:
      1. That it is superseded by PR #21.
      2. Which unique content will be reintroduced in a future milestone.
    """

    def test_pr_22_has_supersedence_comment(self):
        """PR #22 must have a comment referencing #21 and naming a future milestone."""
        ok, reason = _has_supersedence_comment(22)
        self.assertTrue(ok, reason)

    def test_pr_23_has_supersedence_comment(self):
        """PR #23 must have a comment referencing #21 and naming a future milestone."""
        ok, reason = _has_supersedence_comment(23)
        self.assertTrue(ok, reason)

    def test_pr_24_has_supersedence_comment(self):
        """PR #24 must have a comment referencing #21 and naming a future milestone."""
        ok, reason = _has_supersedence_comment(24)
        self.assertTrue(ok, reason)

    def test_all_superseded_prs_have_rationale_comments(self):
        """All three PRs must each carry a valid supersedence comment."""
        failures = {}
        for n in SUPERSEDED_PR_NUMBERS:
            ok, reason = _has_supersedence_comment(n)
            if not ok:
                failures[n] = reason
        self.assertEqual(
            failures,
            {},
            f"Missing rationale comments on: {failures}",
        )


# ---------------------------------------------------------------------------
# Tests — superseding PR (#21) remains open / not accidentally closed
# ---------------------------------------------------------------------------


class TestSupersedingPRIntact(unittest.TestCase):
    """Sanity-check that PR #21 was not accidentally closed during cleanup."""

    def test_pr_21_is_not_closed(self):
        """PR #21 (the superseding PR) must NOT be in CLOSED state."""
        state = _pr_state(21)
        self.assertNotEqual(
            state,
            "CLOSED",
            "PR #21 (the superseding PR) was accidentally closed — reopen it.",
        )


if __name__ == "__main__":
    unittest.main()
