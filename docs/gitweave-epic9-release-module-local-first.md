# GitWeave — Epic 9: Release Module (Local‑First MVP)

**Goal:** Provide the ability to create releases from built artifacts and record deployments to environments. Local‑first: all metadata and artifacts stored locally in mounted volumes and Postgres.

---

## Scope (MVP)
- Create a release object tied to a repo and build artifacts (Epic 7).
- Store release notes (plain text/Markdown string).
- Deploy release to an environment (dev/stg/prod defined per org).
- Record deployment status (success/failed) and timestamps.
- REST API to manage releases and deployments.

### Out of Scope (MVP)
- Environment approval gates (manual/automated checks).
- Rollbacks (manual metadata edits only).
- Multi‑region or multi‑cluster deployment strategies.
- Release pipelines with progressive rollout (blue/green, canary).
- Integration with external infra (Kubernetes, VM, serverless).

---

## Personas
- **Developer**: Publishes a release for their repo and deploys to dev.
- **Release Manager**: Deploys release to staging/prod environments.

---

## Architecture (Local‑First)
- Release service in `app` container manages release objects.
- Links to artifacts stored under `/data/artifacts`.
- Deployments recorded in Postgres.
- For MVP, “deployment” is metadata only (no actual infra change).

---

## Data Model (SQL)
- **releases**(id uuid PK, repo_id, version string, notes text, created_by uuid, created_at)
- **release_artifacts**(release_id, artifact_id, PRIMARY KEY(release_id, artifact_id))
- **environments**(id uuid PK, org_id, name, created_at)
- **deployments**(id uuid PK, release_id, environment_id, status ENUM('success','failed'), started_at, ended_at, deployed_by uuid)

Indexes: repo_id, release_id.

---

## REST API (MVP)
Base path: `/api/v1`

### Releases
- `POST /repos/{repo}/releases` → { version, notes, artifactIds[] }
- `GET /repos/{repo}/releases` → list releases with version, created_at.
- `GET /repos/{repo}/releases/{id}` → details (notes, artifacts, deployments).

### Deployments
- `POST /repos/{repo}/releases/{id}/deployments` → { environmentId } ⇒ creates deployment record (status=success by default in MVP).
- `GET /repos/{repo}/releases/{id}/deployments` → list deployments.
- `GET /deployments/{id}` → details.

---

## Acceptance Criteria
- Can create a release with artifacts attached.
- Release metadata retrievable via API.
- Can “deploy” release to dev/stg/prod environment (record only).
- Deployment record stored and status queryable.
- Deployment appears linked to release.

---

## Test Plan
- Unit: release version validator, artifact linking logic.
- Integration: create release, attach artifacts, deploy to environment.
- E2E: build artifact → release → deploy to dev → deployment appears in API.

---

## Config (env)
```
RELEASE_NOTES_MAX_LEN=5000
```

---

## Future (Post‑MVP)
- Actual infra deployments (Kubernetes, VMs, serverless).
- Rollback mechanism with history tracking.
- Approvals and gates for environments.
- Progressive rollout strategies (canary, blue/green).
- Automated release notes from commits/issues.
- Environment‑specific secrets and service connections (Epic 11).
