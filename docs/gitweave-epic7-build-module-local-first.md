# GitWeave — Epic 7: Build Module (Local‑First MVP)

**Goal:** Provide the first opinionated CI/CD stage — builds. Enable repositories to produce build outputs (artifacts) via templates, running locally within the GitWeave pipeline system.

---

## Scope (MVP)
- Support build jobs from templates (Epic 5 + Epic 6).
- Build jobs can produce output directories/files.
- Store metadata about produced artifacts (name, path, checksum).
- Local filesystem storage of artifacts (mounted volume).
- REST API for listing build runs and produced artifacts.

### Out of Scope (MVP)
- Remote artifact storage (S3, GCS, etc.).
- Advanced caching (rebuild skipping, layered caching).
- Build matrix (single job only in MVP).
- Provenance/SBOM generation (future feature).
- Language‑specific buildpack support (custom templates only).

---

## Personas
- **Developer**: Runs builds for repo and downloads artifacts locally.
- **Platform Engineer**: Defines build templates to ensure consistency across repos.

---

## Architecture (Local‑First)
- Build jobs run inside runner containers (Epic 6).
- Artifacts written to `/data/artifacts/<repo>/<runId>/`.
- Metadata stored in Postgres for retrieval.
- Exposed via REST API for download.

---

## Data Model (SQL)
- **builds**(id uuid PK, run_id, repo_id, status ENUM('success','failed'), started_at, ended_at, triggered_by uuid)
- **artifacts**(id uuid PK, build_id, name, path, checksum sha256, size int, created_at)

Indexes: run_id, repo_id.

Filesystem layout:
```
/data/artifacts/
  repo1/
    run123/
      artifact1.zip
```

---

## REST API (MVP)
Base path: `/api/v1`

### Builds
- `GET /repos/{repo}/builds` → list builds with status and timestamps.
- `GET /repos/{repo}/builds/{id}` → build details (status, artifacts).

### Artifacts
- `GET /repos/{repo}/builds/{id}/artifacts` → list artifacts (name, checksum, size).
- `GET /repos/{repo}/builds/{id}/artifacts/{artifactName}` → download artifact file.

---

## Acceptance Criteria
- Repo with build template can trigger build pipeline.
- Build produces artifact file in local storage.
- Metadata stored and retrievable via API.
- Artifact can be downloaded locally.

---

## Test Plan
- Unit: artifact metadata writer, checksum validator.
- Integration: run build job, write artifact, list/download via API.
- E2E: repo build pipeline produces artifact, developer downloads artifact to local machine.

---

## Config (env)
```
ARTIFACTS_DIR=/data/artifacts
```

---

## Future (Post‑MVP)
- Remote artifact storage (S3/GCS/Azure).
- Build caching (layered builds, cache mounts).
- Provenance/SBOM metadata for supply chain security.
- Build matrix (multi‑platform/language).
- Artifact retention policies and cleanup.
