# GitWeave — Epic 6: Pipeline Runner & Interpreter (Local‑First MVP)

**Goal:** Provide the execution engine for running build, test, and release templates (Epic 5). Local‑first design so developers can run pipelines fully in Docker compose without requiring cloud infrastructure.

---

## Scope (MVP)
- Register runners (local only; one runner service container).
- Execute pipeline templates (build/test/release) defined in Epic 5.
- Job execution model: sequential steps (no parallelism initially).
- Collect logs and job exit codes.
- Expose pipeline run history (status, start/end time, logs).
- REST API for triggering and viewing runs.

### Out of Scope (MVP)
- Multi‑runner clusters / autoscaling.
- Parallel execution / DAG scheduling.
- Secrets injection (stub only; to be added with Epic 11).
- Advanced caching (only basic workspace reuse in MVP).
- Artifact upload (handled in Epic 7).

---

## Personas
- **Developer**: Push to repo triggers pipeline, views logs.
- **DevEx Engineer**: Monitors pipeline execution, inspects failures.

---

## Architecture (Local‑First)
- **runner‑svc** container executes jobs inside lightweight containers (Docker-in-Docker for local).
- **pipeline‑svc** orchestrates: reads template, spawns jobs sequentially, stores logs in Postgres.
- **api‑gateway** proxies run/trigger requests.
- Local: single runner container registered at startup.

---

## Data Model (SQL)
- **pipeline_runs**(id uuid PK, repo_id, template_id, status ENUM('queued','running','success','failed'), started_at, ended_at, triggered_by uuid)
- **jobs**(id uuid PK, run_id, name, status ENUM('queued','running','success','failed'), exit_code int, started_at, ended_at)
- **logs**(id uuid PK, job_id, offset int, chunk text)

Indexes: run_id, job_id.

---

## REST API (MVP)
Base path: `/api/v1`

### Runs
- `POST /repos/{repo}/pipelines/run` → triggers pipeline (using attached templates).
- `GET /repos/{repo}/pipelines/runs` → list runs (status, timestamps).
- `GET /pipelines/runs/{id}` → run details (jobs, status).
- `GET /jobs/{id}/logs` → logs stream (paginated chunks).

---

## Execution Flow
1. Repo has attached template (Epic 5).
2. User triggers run (`POST /repos/.../run`).
3. pipeline‑svc retrieves template body, expands inputs, creates run record.
4. runner‑svc executes each job sequentially inside Docker.
5. Logs streamed back and stored in DB.
6. Status updated at completion.

---

## Acceptance Criteria
- Can trigger a run on a repo with an attached template.
- Logs for each job viewable via API.
- Run status transitions (queued → running → success/failed) correctly.
- Failure in a job marks run as failed and stops subsequent jobs.

---

## Test Plan
- Unit: job executor, log chunker, status state machine.
- Integration: run pipeline with multiple jobs; inspect logs and status.
- E2E: push commit to repo triggers build pipeline; logs retrievable.

---

## Config (env)
```
RUNNER_CONTAINER_ENGINE=docker
RUNNER_WORKDIR=/tmp/gitweave-runs
```

---

## Future (Post‑MVP)
- Parallel job execution / DAG scheduler.
- Multiple runner registration and labels.
- Remote runners over gRPC.
- Secrets and service connections injection (Epic 11).
- Artifact caching and reuse.
- UI for pipeline visualization.
