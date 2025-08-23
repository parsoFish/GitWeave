# GitWeave — Epic 10: Artifact Storage & Package Management (Local‑First MVP)

**Goal:** Provide local storage and management of build artifacts produced in pipelines (Epic 7). Package registry features are deferred, but artifacts must be retrievable for testing and release flows.

---

## Scope (MVP)
- Store artifacts on local filesystem (`/data/artifacts`).
- Track artifacts in Postgres (metadata only).
- API for listing and downloading artifacts by repo and build ID.
- Retention: artifacts persist until manually deleted.
- Download via API or direct file link.
- Checksum validation on upload.

### Out of Scope (MVP)
- Package registry (npm, Maven, PyPI, Docker images).
- Retention/cleanup policies (manual cleanup only).
- Access control beyond repo permissions (MVP reuses repo ACLs).
- Provenance/SBOM (future security features).
- Artifact promotion between environments.

---

## Personas
- **Developer**: Downloads artifacts from builds to run/test locally.
- **Release Manager**: Attaches artifacts to releases for deployment.

---

## Architecture (Local‑First)
- Artifact files stored in `/data/artifacts/<repo>/<buildId>/`.
- Metadata in Postgres (size, checksum, created_at).
- Exposed via REST API in `app` container.
- Download served by API gateway.

---

## Data Model (SQL)
- **artifacts**(id uuid PK, build_id, repo_id, name, path, size int, checksum sha256, created_at)
- **artifact_downloads**(artifact_id, user_id, downloaded_at)

Filesystem layout:
```
/data/artifacts/
  repo1/
    build123/
      artifact1.zip
      artifact2.tar.gz
```

---

## REST API (MVP)
Base path: `/api/v1`

- `GET /repos/{repo}/artifacts` → list all artifacts for repo.
- `GET /repos/{repo}/builds/{buildId}/artifacts` → list artifacts for build.
- `GET /repos/{repo}/artifacts/{artifactId}` → artifact details.
- `GET /repos/{repo}/artifacts/{artifactId}/download` → download file.

---

## Acceptance Criteria
- Build produces artifact; file stored under repo/build folder.
- Metadata persisted in DB (size, checksum, path).
- Artifact retrievable via API download.
- Unauthorized access blocked by repo permissions.

---

## Test Plan
- Unit: checksum validator, metadata writer.
- Integration: run build, upload artifact, download via API.
- E2E: pipeline build produces artifact, release consumes artifact.

---

## Config (env)
```
ARTIFACTS_DIR=/data/artifacts
ARTIFACT_MAX_SIZE_MB=500
```

---

## Future (Post‑MVP)
- Package registries (npm, Maven, PyPI, Docker).
- Retention and cleanup policies (time‑based, size‑based).
- Access control on artifacts (per‑artifact or team‑based).
- Provenance and SBOM integration.
- Artifact promotion flows across environments.
