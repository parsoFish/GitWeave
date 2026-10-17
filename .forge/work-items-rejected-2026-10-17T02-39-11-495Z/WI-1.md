---
work_item_id: WI-1
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on: []
domain: hygiene
acceptance_criteria:
  - given: "the .gitignore file"
    when: "git ls-files gitweave.egg-info runs"
    then: "it produces no output; git check-ignore gitweave.egg-info/SOURCES.txt exits zero"
  - given: "an org whose plan endpoint returns 403 with a rulesets-unsupported body"
    when: "gw plan --json runs"
    then: "the rulesets field in JSON output is reported as unsupported with the API error message; exit 0"
  - given: "an org where the 403 indicates a missing token permission (not plan-lacking-rulesets)"
    when: "gw plan runs"
    then: "gw plan exits non-zero and prints the name of the missing permission"
  - given: "the rulesets manager source code"
    when: "grep runs over gitweave/managers/rulesets.py"
    then: "no line contains the string '403' inside str(exc) string matching; the two 403 cases are distinguished by response body content or exception type, not string coercion"
files_in_scope:
  - .gitignore
  - gitweave/managers/rulesets.py
  - tests/test_structure.py
  - tests/test_rulesets_unsupported_plan.py
verification_artifact: tests/test_rulesets_unsupported_plan.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_structure.py"
  - "tests/test_rulesets_unsupported_plan.py"
  - "-k"
  - "test_egg_info_gitignored or test_403_permission_denied_exits_nonzero"
  - "-p"
  - "no:cacheprovider"
---

# WI-1: Ground hygiene — egg-info .gitignore + rulesets 403 split

Target: `.gitignore` and `gitweave/managers/rulesets.py` in the project root.

## Work

### 1. gitweave.egg-info in .gitignore

Add `gitweave.egg-info/` to `.gitignore`. After this:
- `git ls-files gitweave.egg-info` must produce no output
- `git check-ignore gitweave.egg-info/SOURCES.txt` must exit zero

Add a new test method `test_egg_info_gitignored` to the relevant class in `tests/test_structure.py`:

```python
def test_egg_info_gitignored(self):
    result = subprocess.run(
        ["git", "ls-files", "gitweave.egg-info"],
        capture_output=True, text=True
    )
    self.assertEqual(result.stdout.strip(), "",
        "gitweave.egg-info/ must be gitignored")
    result2 = subprocess.run(
        ["git", "check-ignore", "gitweave.egg-info/SOURCES.txt"],
        capture_output=True, text=True
    )
    self.assertEqual(result2.returncode, 0,
        "gitweave.egg-info/SOURCES.txt must be gitignored")
```

### 2. Rulesets 403 split

Current code in `gitweave/managers/rulesets.py` uses `"403" in str(exc)` string matching — remove this.

Split into two distinct cases by inspecting the response body:
- **org-plan-lacks-rulesets**: API returns 403 with a body mentioning the org plan lacks rulesets support → set rulesets field to `{"status": "unsupported", "message": "<api_error_message>"}`, exit 0.
- **missing-token-permission**: API returns 403 for a permissions reason (different body) → exit non-zero, print the missing permission name.

In `tests/test_rulesets_unsupported_plan.py`, add:
- A test for the org-plan case (already likely partially tested; extend/rename)
- A new test `test_403_permission_denied_exits_nonzero` that patches the API to return 403 with a permissions error body and asserts exit code 1 + permission name in stderr

Examine the existing test class name in `tests/test_rulesets_unsupported_plan.py` and add the new test method to it.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
