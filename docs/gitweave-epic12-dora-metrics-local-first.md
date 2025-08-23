# GitWeave — Epic 12: Built‑in DORA Metrics (Local‑First MVP)

**Goal:** Provide native computation of DORA metrics (Deployment Frequency, Lead Time for Changes, Mean Time to Restore, Change Failure Rate) directly from GitWeave platform data, without requiring external integrations. Runs locally with Postgres and API endpoints.

---

## Scope (MVP)
- Compute **Deployment Frequency (DF)**: count successful deployments (Epic 9) over time window.
- Compute **Lead Time for Changes (LT)**: time from commit to deployment (commit timestamp → successful deployment timestamp).
- Store computed snapshots in Postgres, refreshed on demand.
- REST API for querying metrics (org/project/repo scope).
- Basic aggregation: daily/weekly.
- Local‑first: metrics recompute on API request.

### Out of Scope (MVP)
- Automatic incremental computation (manual refresh only in MVP).
- MTTR and CFR (require incident + failure tracking; deferred).
- Visual dashboards (API only).
- Team attribution (only repo/org rollups in MVP).
- Benchmarks/targets (alerts, thresholds).

---

## Personas
- **Engineering Manager / DevEx**: Queries metrics to understand delivery performance.
- **Developer**: Can see lead time from commit to deploy for their repo.

---

## Architecture (Local‑First)
- Metrics service inside `app` container.
- Reads from repos (Epic 3), commits, pipeline runs (Epic 6), releases/deployments (Epic 9).
- Snapshots computed and stored in Postgres for caching.
- Local dev: API endpoints recompute directly from DB.

---

## Data Model (SQL)
- **dora_snapshots**(id uuid PK, scope_type ENUM('org','project','repo'), scope_id, period_start date, period_end date, deployment_frequency int, lead_time_avg_ms bigint, created_at)
- **dora_events** (optional future) for incremental calc.

---

## REST API (MVP)
Base path: `/api/v1`

- `GET /metrics/dora?scope=repo&id=<repo>&from=2024-01-01&to=2024-01-31` → { DF, LT_avg }
- `POST /metrics/dora/recompute` → triggers recompute for scope/time window.

Example response:
```json
{
  "deployment_frequency": 12,
  "lead_time_avg_hours": 5.6
}
```

---

## Acceptance Criteria
- API recomputes metrics for repo/org from commits + deployments.
- DF = deployments per week/month; LT = commit → deploy lag average.
- Metrics visible for repo with real commit/deploy data.
- No external integrations required.

---

## Test Plan
- Unit: DF calculator, LT calculator.
- Integration: repo with 3 commits, 2 deployments → metrics reflect counts and averages.
- E2E: developer pushes commit, release deployed, recompute shows LT.

---

## Config (env)
_No new config for MVP._

---

## Future (Post‑MVP)
- MTTR (mean time to restore service) from incident tracking or failed → fixed deployments.
- CFR (change failure rate) from failed deployments.
- Incremental updates (real‑time metrics).
- Visualization dashboards in UI.
- Team‑scoped metrics (from work items + repos).
- Benchmarks and alerting on thresholds.
