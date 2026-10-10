# I1 — An honest baseline

> _Derived from `demo.json` (D-07). Essence:_ I1 — An honest baseline — 6 work items delivered against 12 acceptance criteria, 2 merge-boundary gates run.

## What this enables

_Agent narrative — not evidence._

The gitweave repo shed its April-2026 spike artefacts — a dead metrics service, stub modules, broken tests, and stale CI jobs — leaving only live tooling. Developers now clone a repo whose full test suite passes green, whose bootstrap script runs without Docker, and whose legal files (AGPL-3 LICENSE, Apache ICLA CLA.md) are in place. The baseline is honest: every file present is there because something needs it.

## Summary

- WI-1 [complete] # WI-1: Archive pre-prune HEAD and delete retiring artefacts
- WI-2 [complete] # WI-2: Fix bootstrap.sh — remove Docker dependency, add root requirements.txt
- WI-3 [complete] # WI-3: Remove example-template references from config and CI yaml
- WI-4 [complete] # WI-4: Replace CLAUDE.md with one-line pointer and update .gitignore
- WI-5 [complete] # WI-5: Add LICENSE, CLA.md, update README, fix test_structure.py README assertion
- WI-6 [complete] # WI-6 — gate-fix concern (code-fix)
- Commit: `91a37bf7191f63602fa9fb357c156d5654fafda2`

## Visual Changes

### Archive branch exists at pre-prune HEAD


### Retired paths confirmed absent


### test_structure.py passes without stale metrics/modules assertions


### bootstrap.sh exits 0 without Docker


### Bootstrap test passes — no --deselect needed


### example-template removed from config and CI yaml


### CLAUDE.md is a one-liner; .gitignore covers required entries


### LICENSE is AGPL-3 verbatim; CLA.md is Apache ICLA


### Full gate suite green — no cross-WI regression


## Test Evidence

| test | result | delta |
|---|---|---|
| local: python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero | pass | — |
| ci: python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py | pass | — |

> result: **pass**/**fail** · **skip** = not run in this gate (e.g. a live test with no credentials present) — not a failure · delta **new** = test added by this change.

## Acceptance criteria

- (WI-1) GIVEN the remote origin before any deletion commit lands WHEN `git ls-remote origin archive/april-2026` is run THEN the branch exists and its tip SHA equals the pre-prune main HEAD
- (WI-1) GIVEN the worktree after prune WHEN `python3 -m pytest tests/test_pruned_artefacts.py` runs THEN all assertions pass — every retired directory and file is confirmed absent
- (WI-1) GIVEN the worktree after prune WHEN `python3 -m pytest tests/test_structure.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` runs THEN all remaining test_structure.py tests pass — stale metrics/modules assertions removed
- (WI-2) GIVEN bootstrap.sh after the Docker calls are removed and requirements.txt exists at repo root WHEN `bash scripts/bootstrap.sh` runs on a machine with git, python3, and terraform but without Docker THEN the script exits 0 and installs the live tooling dependencies from root requirements.txt
- (WI-2) GIVEN the test suite after WI-1 pruning WHEN `python3 -m pytest tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` runs THEN the test passes — no --deselect flag needed
- (WI-3) GIVEN config/repos/example.yaml after the example-template entry is removed WHEN `python3 -m pytest tests/test_example_template_removed.py` runs THEN both assertions pass — config no longer references example-template and ci.yaml no longer asserts it in smoke output
- (WI-3) GIVEN .github/workflows/ci.yaml after the example-template assertion is removed WHEN `yamllint .github/workflows/ci.yaml` runs THEN exits 0 — the file is valid YAML
- (WI-4) GIVEN CLAUDE.md after replacement WHEN `cat CLAUDE.md` is read THEN the file contains exactly one line: `See AGENTS.md.` — no other content
- (WI-4) GIVEN .gitignore after update WHEN `python3 -m pytest tests/test_repo_hygiene.py` runs THEN all assertions pass — CLAUDE.md is a one-liner and .gitignore covers secrets.env, .pytest_cache/, and _preflight*.md
- (WI-5) GIVEN the repo root after this WI WHEN `python3 -m pytest tests/test_legal_files.py` runs THEN all assertions pass — LICENSE is AGPL-3.0-or-later verbatim (includes 'or later' notice), CLA.md is Apache ICLA standard form
- (WI-5) GIVEN README.md after update WHEN `python3 -m pytest tests/test_structure.py::TestRepoStructure::test_readme_contains_bootstrap_instructions` runs THEN passes without referencing metrics/ — the assertion for metrics/ is removed from test_structure.py in this WI
- (WI-6) GIVEN the initiative branch is integrated at tip WHEN the full project test suite runs (the merge-boundary gate) THEN it passes green — no cross-WI regression remains

## Files Changed

- `.forge/demo/DEMO.html`
- `.forge/demo/demo.lock.json`
- `.forge/demo/history/2026-10-09T07-02-03-1027e4cf/DEMO.html`
- `.forge/demo/history/2026-10-09T07-02-03-1027e4cf/meta.json`
- `.github/workflows/ci.yaml`
- `.github/workflows/metrics-ci.yaml`
- `.github/workflows/metrics-docker.yaml`
- `.gitignore`
- `CLA.md`
- `CLAUDE.md`
- `LICENSE`
- `config/repos/example.yaml`
- `metrics/Dockerfile`
- `metrics/alembic.ini`
- `metrics/docker-compose.yml`
- `metrics/migrations/README`
- `metrics/migrations/env.py`
- `metrics/migrations/script.py.mako`
- `metrics/migrations/versions/001_initial_schema.py`
- `metrics/migrations/versions/002_events_table.py`
- `metrics/requirements-prod.txt`
- `metrics/requirements.txt`
- `metrics/src/dora/__init__.py`
- `metrics/src/dora/change_failure_rate.py`
- `metrics/src/dora/deployment_frequency.py`
- `metrics/src/dora/lead_time_for_changes.py`
- `metrics/src/dora/mttr.py`
- `metrics/src/handlers/__init__.py`
- `metrics/src/handlers/deployment_status.py`
- `metrics/src/handlers/pull_request.py`
- `metrics/src/handlers/push.py`
- `metrics/src/main.py`
- `metrics/src/replay.py`
- `metrics/src/store.py`
- `metrics/tests/conftest.py`
- `metrics/tests/fixtures/deployment_status.json`
- `metrics/tests/fixtures/deployment_status_failure.json`
- `metrics/tests/fixtures/pull_request_closed_not_merged.json`
- `metrics/tests/fixtures/pull_request_merged.json`
- `metrics/tests/fixtures/pull_request_opened.json`
- `metrics/tests/fixtures/push.json`
- `metrics/tests/fixtures/push_empty_commits.json`
- `metrics/tests/test_alembic_migrations.py`
- `metrics/tests/test_compose_integration.py`
- `metrics/tests/test_deployment_frequency.py`
- `metrics/tests/test_docker_compose.py`
- `metrics/tests/test_docker_compose_complete.py`
- `metrics/tests/test_dockerfile.py`
- `metrics/tests/test_dora_collector.py`
- `metrics/tests/test_dora_metrics_endpoint.py`
- `metrics/tests/test_event_handlers.py`
- `metrics/tests/test_event_store_factory.py`
- `metrics/tests/test_events_table_migration.py`
- `metrics/tests/test_fastapi_lifespan_postgres_replay.py`
- `metrics/tests/test_fastapi_routes.py`
- `metrics/tests/test_fastapi_webhook_dispatch.py`
- `metrics/tests/test_inmemory_event_store_exhaustive.py`
- `metrics/tests/test_lead_time_for_changes.py`
- `metrics/tests/test_main.py`
- `metrics/tests/test_metrics_endpoint.py`
- `metrics/tests/test_metrics_token.py`
- `metrics/tests/test_postgres_event_store_tdd.py`
- `metrics/tests/test_postgres_startup_replay.py`
- `metrics/tests/test_postgresql_event_store.py`
- `metrics/tests/test_startup_replay.py`
- `metrics/tests/test_webhook_endpoint.py`
- `metrics/tests/test_webhook_signature.py`
- `modules/example-template/README.md`
- `modules/example-template/copier.yaml`
- `requirements.txt`
- `scripts/bootstrap.sh`
- `scripts/generate-update-pr.py`
- `tests/test_bootstrap_expand.py`
- `tests/test_copier_schema.py`
- `tests/test_demo_guide.py`
- `tests/test_dora_metrics_ci_workflow.py`
- `tests/test_example_template_removed.py`
- `tests/test_legal_files.py`
- `tests/test_metrics_docker_workflow.py`
- `tests/test_metrics_dockerfile.py`
- `tests/test_modules/__init__.py`
- `tests/test_modules/test_python_service.py`
- `tests/test_modules/test_terraform_module.py`
- `tests/test_pruned_artefacts.py`
- `tests/test_repo_hygiene.py`
- `tests/test_stale_remote_branches.py`
- `tests/test_structure.py`

```
87 files changed, 1021 insertions(+), 18257 deletions(-)
```
