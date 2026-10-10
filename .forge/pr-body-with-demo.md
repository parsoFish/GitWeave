# I1 — An honest baseline

Initiative `INIT-2026-10-10-i1-honest-baseline` · project `gitweave` · head `91a37bf7191f63602fa9fb357c156d5654fafda2`

## Why

The acceptance criteria this initiative was decomposed against:

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

## What

- **WI-1** [complete] # WI-1: Archive pre-prune HEAD and delete retiring artefacts
- **WI-2** [complete] # WI-2: Fix bootstrap.sh — remove Docker dependency, add root requirements.txt
- **WI-3** [complete] # WI-3: Remove example-template references from config and CI yaml
- **WI-4** [complete] # WI-4: Replace CLAUDE.md with one-line pointer and update .gitignore
- **WI-5** [complete] # WI-5: Add LICENSE, CLA.md, update README, fix test_structure.py README assertion
- **WI-6** [complete] # WI-6 — gate-fix concern (code-fix)

```
87 files changed, 1021 insertions(+), 18257 deletions(-)
```

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

## How

Merge-boundary gates the orchestrator ran:

- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` (local) — pass
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py` (ci) — pass

Evidence captured:

- `git ls-remote origin archive/april-2026` — Archive branch exists at pre-prune HEAD (unchanged)
- `python3 -m pytest tests/test_pruned_artefacts.py` — Retired paths confirmed absent (changed)

```
- collected 0 items
+ collected 6 items
- ============================ no tests ran in <duration> =============================
+ tests/test_pruned_artefacts.py ......                                    [100%]
- [stderr] ERROR: file or directory not found: tests/test_pruned_artefacts.py
+ 
+ ============================== 6 passed in <duration> ===============================
+ 
```
- `python3 -m pytest tests/test_structure.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` — test_structure.py passes without stale metrics/modules assertions (unchanged)
- `bash scripts/bootstrap.sh` — bootstrap.sh exits 0 without Docker (changed)

```
-   docker ... ok
+ 
-   docker daemon ... running
+ Verifying directory structure...
- 
+   modules ... ok
- Verifying directory structure...
+   config ... ok
-   modules ... ok
+   infra ... ok
-   config ... ok
+   WARNING: 'metrics' missing — creating...
-   infra ... ok
+   .github/workflows ... ok
-   metrics ... ok
+ 
-   .github/workflows ... ok
+ Initialising Terraform (terraform init)...
- 
+ [0m[1mInitializing the backend...[0m
- Starting metrics stack (docker compose up -d)...
+ [0m[1mInitializing provider plugins...[0m
- [stderr] time="<timestamp>" level=warning msg="Found orphan containers (metrics-grafana-1, metrics-prometheus-1) for this project. If you removed or renamed this service in your compose file, you can run this command with the --remove-orphans flag to clean it up."
+ - Finding integrations/github versions matching "~> 6.0"...
-  Container metrics-postgres-1 Starting 
+ - Installing integrations/github v6.13.0...
-  Container metrics-postgres-1 Started 
+ - Installed integrations/github v6.13.0 (signed by a HashiCorp partner, key ID [0m[1m38027F80D7FD5FB2[0m[0m)
-  Container metrics-postgres-1 Waiting 
+ Partner and community providers are sig
…[truncated]
```
- `python3 -m pytest tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero` — Bootstrap test passes — no --deselect needed (changed)

```
- tests/test_structure.py F                                                [100%]
+ tests/test_structure.py .                                                [100%]
- =================================== FAILURES ===================================
+ ============================== 1 passed in <duration> ===============================
- ______________ TestRepoStructure.test_bootstrap_script_exits_zero ______________
+ 
- 
- self = <test_structure.TestRepoStructure testMethod=test_bootstrap_script_exits_zero>
- 
-     def test_bootstrap_script_exits_zero(self):
-         """bootstrap.sh should succeed when all prerequisites (git, terraform, python3) are present."""
-         script = os.path.join(self.repo_root, 'scripts', 'bootstrap.sh')
-         self.assertTrue(os.path.isfile(script), "scripts/bootstrap.sh is missing")
-         result = subprocess.run(
-             ['bash', script],
-             capture_output=True,
-             text=True,
-             cwd=self.repo_root,
-         )
- >       self.assertEqual(
-             result.returncode,
-             0,
-             f"bootstrap.sh exited {result.returncode}:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}",
-        
…[truncated]
```
- `python3 -m pytest tests/test_example_template_removed.py` — example-template removed from config and CI yaml (changed)

```
- collected 0 items
+ collected 2 items
- ============================ no tests ran in <duration> =============================
+ tests/test_example_template_removed.py ..                                [100%]
- [stderr] ERROR: file or directory not found: tests/test_example_template_removed.py
+ 
+ ============================== 2 passed in <duration> ===============================
+ 
```
- `python3 -m pytest tests/test_repo_hygiene.py` — CLAUDE.md is a one-liner; .gitignore covers required entries (changed)

```
- collected 0 items
+ collected 4 items
- ============================ no tests ran in <duration> =============================
+ tests/test_repo_hygiene.py ....                                          [100%]
- [stderr] ERROR: file or directory not found: tests/test_repo_hygiene.py
+ 
+ ============================== 4 passed in <duration> ===============================
+ 
```
- `python3 -m pytest tests/test_legal_files.py` — LICENSE is AGPL-3 verbatim; CLA.md is Apache ICLA (changed)

```
- collected 0 items
+ collected 6 items
- ============================ no tests ran in <duration> =============================
+ tests/test_legal_files.py ......                                         [100%]
- [stderr] ERROR: file or directory not found: tests/test_legal_files.py
+ 
+ ============================== 6 passed in <duration> ===============================
+ 
```
- `python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero -q` — Full gate suite green — no cross-WI regression (changed)

```
- ........................................................................ [ 51%]
+ ........................................................................ [ 52%]
- .....................................................................   [100%]
+ ................................................................         [100%]
- 141 passed, 1 deselected, 1 subtests passed in <duration>
+ 136 passed, 1 deselected in <duration>
```

7 of 9 captured checkpoints changed behaviour. Command output compared after normalising: tap-duration, duration, iso-timestamp, worktree path.

_Derived by forge from the acceptance criteria, the gate evidence and the diff — not authored by an agent._

---

## Demo

▶ **[Open the rendered demo: `demo/INIT-2026-10-10-i1-honest-baseline/DEMO.md`](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/DEMO.md)** — renders inline on GitHub (works for private repos too).

The screenshots are also visible in this PR's **Files changed** tab (committed under `demo/INIT-2026-10-10-i1-honest-baseline/`).

Demo artefacts:
- [`DEMO.md`](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/DEMO.md)
- [`demo-plan.json`](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/demo-plan.json)
- [`demo.json`](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/demo.json)


### Captured checkpoints

**Plan-1-WI-1-1yki11**

![Plan-1-WI-1-1yki11 — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-1-WI-1-1yki11.filmstrip.png?raw=true)

![Plan-1-WI-1-1yki11 — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.filmstrip.png?raw=true)

[▶ Plan-1-WI-1-1yki11 — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-1-WI-1-1yki11.webm)

[▶ Plan-1-WI-1-1yki11 — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-1-WI-1-1yki11.webm)

**Plan-2-WI-1-e7s99z**

![Plan-2-WI-1-e7s99z — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-2-WI-1-e7s99z.filmstrip.png?raw=true)

![Plan-2-WI-1-e7s99z — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-2-WI-1-e7s99z.filmstrip.png?raw=true)

[▶ Plan-2-WI-1-e7s99z — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-2-WI-1-e7s99z.webm)

[▶ Plan-2-WI-1-e7s99z — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-2-WI-1-e7s99z.webm)

**Plan-3-WI-1-sw6ji0**

![Plan-3-WI-1-sw6ji0 — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-3-WI-1-sw6ji0.filmstrip.png?raw=true)

![Plan-3-WI-1-sw6ji0 — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-3-WI-1-sw6ji0.filmstrip.png?raw=true)

[▶ Plan-3-WI-1-sw6ji0 — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-3-WI-1-sw6ji0.webm)

[▶ Plan-3-WI-1-sw6ji0 — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-3-WI-1-sw6ji0.webm)

**Plan-4-WI-2-17kktq**

![Plan-4-WI-2-17kktq — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-4-WI-2-17kktq.filmstrip.png?raw=true)

![Plan-4-WI-2-17kktq — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-4-WI-2-17kktq.filmstrip.png?raw=true)

[▶ Plan-4-WI-2-17kktq — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-4-WI-2-17kktq.webm)

[▶ Plan-4-WI-2-17kktq — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-4-WI-2-17kktq.webm)

**Plan-5-WI-2-1m8z3y**

![Plan-5-WI-2-1m8z3y — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-5-WI-2-1m8z3y.filmstrip.png?raw=true)

![Plan-5-WI-2-1m8z3y — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-5-WI-2-1m8z3y.filmstrip.png?raw=true)

[▶ Plan-5-WI-2-1m8z3y — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-5-WI-2-1m8z3y.webm)

[▶ Plan-5-WI-2-1m8z3y — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-5-WI-2-1m8z3y.webm)

**Plan-6-WI-3-1w9c71**

![Plan-6-WI-3-1w9c71 — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-6-WI-3-1w9c71.filmstrip.png?raw=true)

![Plan-6-WI-3-1w9c71 — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-6-WI-3-1w9c71.filmstrip.png?raw=true)

[▶ Plan-6-WI-3-1w9c71 — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-6-WI-3-1w9c71.webm)

[▶ Plan-6-WI-3-1w9c71 — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-6-WI-3-1w9c71.webm)

**Plan-7-WI-4-gknmf3**

![Plan-7-WI-4-gknmf3 — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-7-WI-4-gknmf3.filmstrip.png?raw=true)

![Plan-7-WI-4-gknmf3 — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-7-WI-4-gknmf3.filmstrip.png?raw=true)

[▶ Plan-7-WI-4-gknmf3 — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-7-WI-4-gknmf3.webm)

[▶ Plan-7-WI-4-gknmf3 — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-7-WI-4-gknmf3.webm)

**Plan-8-WI-5-v91wn5**

![Plan-8-WI-5-v91wn5 — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-8-WI-5-v91wn5.filmstrip.png?raw=true)

![Plan-8-WI-5-v91wn5 — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-8-WI-5-v91wn5.filmstrip.png?raw=true)

[▶ Plan-8-WI-5-v91wn5 — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-8-WI-5-v91wn5.webm)

[▶ Plan-8-WI-5-v91wn5 — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-8-WI-5-v91wn5.webm)

**Plan-9-WI-6-19xg6v**

![Plan-9-WI-6-19xg6v — before](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-9-WI-6-19xg6v.filmstrip.png?raw=true)

![Plan-9-WI-6-19xg6v — after](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-9-WI-6-19xg6v.filmstrip.png?raw=true)

[▶ Plan-9-WI-6-19xg6v — before (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/before/Plan-9-WI-6-19xg6v.webm)

[▶ Plan-9-WI-6-19xg6v — after (webm)](https://github.com/parsoFish/GitWeave/blob/39ad991bc9658a5510ce578f381a34d3ab6aafa2/demo/INIT-2026-10-10-i1-honest-baseline/.capture/after/Plan-9-WI-6-19xg6v.webm)

