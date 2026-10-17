---
work_item_id: WI-8
initiative_id: INIT-2026-10-17-i4-modules-overlays
status: pending
depends_on:
  - WI-6
domain: plan
acceptance_criteria:
  - given: "a recorded fixture containing one repo-without-modules entry and one repo-at-declared-version entry"
    when: "gw plan runs with all GW_* variables unset"
    then: "output lists the module files to add for the repo-without-modules entry; produces no file-change output for the repo-at-declared-version entry; exit 0"
  - given: "scripts/apply-overlays.py exists"
    when: "git ls-files scripts/apply-overlays.py runs after this WI is delivered"
    then: "the file is not tracked; it has been deleted"
  - given: "the CI dry-run-smoke job in .github/workflows/"
    when: "it is inspected"
    then: "it invokes gw plan (not apply-overlays.py); the job still runs credential-free"
  - given: "the offline fixture format"
    when: "it is documented in tests/test_plan_overlay.py module docstring or a comment"
    then: "the format is described: what keys are present, how repos are represented, how applied-module state is recorded"
files_in_scope:
  - gitweave/plan.py
  - scripts/apply-overlays.py
  - tests/test_plan_overlay.py
creates:
  - tests/test_plan_overlay.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_plan_overlay.py::TestPlanOverlay::test_plan_lists_files_for_repo_without_modules"
  - "-p"
  - "no:cacheprovider"
---

# WI-8: gw plan overlay-aware + retire scripts/apply-overlays.py

Target: extend `gitweave/plan.py` with overlay awareness; delete `scripts/apply-overlays.py`; create `tests/test_plan_overlay.py`; update CI.

## gitweave/plan.py extension

Extend `plan()` to include overlay diff output when a fixture is provided.

### Fixture format (document in test file module docstring)

The offline fixture is a dict (JSON or YAML) with the following structure:

```json
{
  "repos": [
    {
      "name": "repo-a",
      "overlay": null
    },
    {
      "name": "repo-b",
      "overlay": {
        "_module_name": "python_service",
        "_module_version": "2026.10.1",
        "_answers": {"service_name": "svc_b"}
      }
    }
  ]
}
```

- `overlay: null` means no `.copier-answers.yml` found (no modules applied)
- `overlay: {...}` means `.copier-answers.yml` content read back from API at fixture capture time

### Plan output for overlay

```
Overlays:
  repo-a: would add [python_service @ 2026.10.1] (6 files)
  repo-b: unchanged (python_service @ 2026.10.1)
```

Repos not in `config/repos/<name>.yaml` with `spec.modules` are omitted from overlay output.

The plan compares the fixture's applied state against `config/repos/<name>.yaml`'s declared modules. A fixture is required for overlay plan (the overlay plan sub-section is skipped if no fixture is provided).

## scripts/apply-overlays.py retirement

Delete `scripts/apply-overlays.py`. This script is replaced by `gw apply` for live runs and `gw plan` for dry-run.

Update `.github/workflows/` CI dry-run-smoke job to invoke `gw plan` (credential-free, using a fixture file checked into the repo or generated from tests/fixtures/). The job must NOT set any GW_* secrets — it runs offline.

## tests/test_plan_overlay.py

Document the fixture format in the module docstring (see "Fixture format" above).

Class `TestPlanOverlay`:
- `test_plan_lists_files_for_repo_without_modules` — builds a fixture with one no-overlay repo declaring `python_service` in its config; runs `plan(fixture_path=...)` offline; asserts output mentions "would add [python_service"
- `test_plan_unchanged_for_matching_repo` — builds fixture where repo's applied state matches declared; asserts output mentions "unchanged"
- `test_plan_no_overlay_section_without_fixture` — calls `plan()` with no fixture; asserts overlay section absent from output
- `test_apply_overlays_py_deleted` — asserts `scripts/apply-overlays.py` does not exist in `git ls-files`

Tests must NOT inherit any GW_* autouse fixture.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
