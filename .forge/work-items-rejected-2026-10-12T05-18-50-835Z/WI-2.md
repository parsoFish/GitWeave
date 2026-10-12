---
work_item_id: WI-2
initiative_id: INIT-2026-10-11-i3a-green-apply-path
status: pending
depends_on: []
acceptance_criteria:
  - given: "the gitweave-apply.yaml workflow file after this WI"
    when: "its dry-run-smoke job (name: 'Apply Configuration') is inspected"
    then: "it does NOT invoke scripts/apply-overlays.py; it either runs gw plan --fixture or is rewired to a gw command, or is removed entirely"
  - given: "the gitweave-apply.yaml workflow file after this WI"
    when: "the apply job env block is inspected"
    then: "GW_RESOURCE_PREFIX is set (e.g. from secrets.GW_RESOURCE_PREFIX or a static value) so gw apply scopes by the ownership marker"
  - given: "the ci.yaml workflow file after this WI"
    when: "its job names are listed"
    then: "jobs named exactly 'Structural Tests' and 'Dry-Run Smoke Test' exist and are not renamed"
files_in_scope:
  - .github/workflows/gitweave-apply.yaml
  - .github/workflows/ci.yaml
  - tests/test_apply_workflow_structure.py
  - tests/test_gw_apply_workflow.py
  - tests/test_ci_workflow.py
  - tests/test_apply_workflow_rewired.py
creates:
  - tests/test_apply_workflow_rewired.py
estimated_iterations: 2
quality_gate_cmd:
  - pytest
  - "-q"
  - "-p"
  - "no:cacheprovider"
  - "tests/test_apply_workflow_rewired.py::TestApplyWorkflowRewired::test_apply_config_no_longer_calls_apply_overlays_py"
domain: ci
---

# WI-2: Fix Apply workflow CI

## Context

`gitweave-apply.yaml` has a broken `dry-run-smoke` job (name: "Apply Configuration") that calls `scripts/apply-overlays.py config/repos/` — a spike stub that cannot handle a directory argument. Post-I2, this job makes the workflow red on every push to main.

Additionally, the live `apply` job runs `gw apply` but does not set `GW_RESOURCE_PREFIX` in its env, so after WI-1 makes GW_RESOURCE_PREFIX required, the live apply job would fail without it.

## What to change

**`.github/workflows/gitweave-apply.yaml`:**

1. `dry-run-smoke` job — remove the broken "Apply Overlays" step that calls `python3 scripts/apply-overlays.py config/repos/`. Replace with a `gw plan --fixture tests/fixtures/org-empty.json` step (requires installing gw via `pip install -e .`). Keep the job name `name: Apply Configuration` ONLY if that is not a required check name; otherwise rename to something accurate. The initiative says: remove or rewire to `gw apply`. Prefer rewiring to `gw plan --fixture` (credential-free) since this job runs on PRs too.

2. `apply` job — add `GW_RESOURCE_PREFIX: ${{ secrets.GW_RESOURCE_PREFIX }}` to its `env:` block alongside the existing GW_ORG etc.

**`.github/workflows/ci.yaml`:**

Read the file and verify job names 'Structural Tests' and 'Dry-Run Smoke Test' exist with exactly those names. If they don't match exactly, rename to match. Do NOT rename a correctly-named job.

**Existing workflow structure tests** (`tests/test_apply_workflow_structure.py`, `tests/test_gw_apply_workflow.py`, `tests/test_ci_workflow.py`):

Read each file. Update any assertions that reference `scripts/apply-overlays.py` as the apply step command. Update assertions about the dry-run-smoke job steps to match the new gw plan invocation. Do NOT break assertions about job names that are already correct.

**`tests/test_apply_workflow_rewired.py` (new):**

Write `TestApplyWorkflowRewired` with:
- `test_apply_config_no_longer_calls_apply_overlays_py` — parse gitweave-apply.yaml and assert no step command contains `apply-overlays.py`
- `test_apply_job_has_gw_resource_prefix_env` — assert the apply job's env contains a `GW_RESOURCE_PREFIX` key
- `test_ci_has_required_job_names` — parse ci.yaml and assert job names include 'Structural Tests' and 'Dry-Run Smoke Test' exactly

Use `yaml.safe_load` and `pathlib.Path` to read workflow files relative to the repo root (find it via `Path(__file__).parent.parent`).

---

**Brain themes consulted:**
- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/design-is-the-bottleneck.md`
- `brain/cycles/themes/work-item-completion-by-domain.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
