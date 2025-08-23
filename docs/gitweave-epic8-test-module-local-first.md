# GitWeave — Epic 8: Test Module (Local‑First MVP)

**Goal:** Provide a standardized way to execute tests as part of pipelines and capture results/coverage locally. Works with opinionated templates (Epic 5) and runs through the runner (Epic 6).

---

## Scope (MVP)
- Execute test jobs defined in templates (unit/integration stages allowed, sequential only).
- Ingest common test report formats: JUnit XML (primary), with a simple parser.
- Optional coverage ingestion: Cobertura/LCOV (store summary only in MVP).
- Store pass/fail counts, duration, and link to pipeline run.
- REST API to query test runs and summaries.
- Display minimal test summary in API responses (counts, duration).

### Out of Scope (MVP)
- Per‑test failure UI with stack traces (store raw XML path; no rich UI yet).
- Flaky test detection, retries, quarantine.
- Parallel test sharding.
- Historical trend dashboards (post‑MVP).


---

## Personas
- **Developer**: Runs tests with build; checks pass/fail and coverage summary.
- **QA/Lead**: Reviews summaries to gate releases (later).

---

## Architecture (Local‑First)
- Runner executes test steps inside containers.
- Test reports written to workspace and uploaded to `/data/test-reports/<repo>/<runId>/`.
- Parser ingests JUnit XML into Postgres (summary only).
- Coverage parser ingests Cobertura/LCOV summary numbers (optional).

---

## Data Model (SQL)
- **test_runs**(id uuid PK, run_id, repo_id, status ENUM('success','failed'), suites int, tests int, failures int, errors int, skipped int, duration_ms int, coverage_percent numeric, report_path text, created_at)
- **test_artifacts**(id uuid PK, test_run_id, name, path, size int, created_at)

Indexes: run_id, repo_id.

Filesystem layout:
```
/data/test-reports/
  repo1/
    run123/
      junit.xml
      coverage.xml
```

---

## REST API (MVP)
Base path: `/api/v1`

- `GET /repos/{repo}/tests` → list test runs (status, counts, coverage, duration).
- `GET /repos/{repo}/tests/{id}` → details (summary + artifact links).
- `GET /repos/{repo}/tests/{id}/artifacts` → list stored files (e.g., junit.xml, coverage files).
- `GET /repos/{repo}/tests/{id}/artifacts/{name}` → download artifact.

---

## Acceptance Criteria
- Pipeline with a test template step produces a JUnit XML report.
- System ingests report into summary rows and stores raw files.
- API exposes summaries and allows downloading raw artifacts.
- Failures mark the test run (and parent pipeline run) failed.

---

## Test Plan
- Unit: JUnit/Cobertura parsers (happy + malformed paths), numeric aggregations.
- Integration: run a pipeline producing junit.xml and coverage; ensure ingestion and API retrieval.
- E2E: failing tests flip run to failed; summaries reflect test counts accurately.

---

## Config (env)
```
TEST_REPORTS_DIR=/data/test-reports
TEST_MAX_XML_SIZE_MB=5
```

---

## Future (Post‑MVP)
- Rich per‑test UI with stack traces and history.
- Flaky test detection, retries/quarantine.
- Parallel execution and sharding.
- Coverage gates (minimum % thresholds) for merges/releases.
- Trend dashboards and alerts.
