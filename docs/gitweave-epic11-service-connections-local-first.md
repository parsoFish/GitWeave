# GitWeave — Epic 11: Service Connections (Local‑First MVP)

**Goal:** Provide a minimal framework for storing and referencing external service credentials (cloud providers, registries, chat integrations). For local‑first MVP, secrets are stored securely in Postgres and injected into pipelines at runtime.

---

## Scope (MVP)
- Define service connections (name, type, credentials JSON).
- Supported types in MVP: generic (key/value), AWS (access key + secret), Docker registry (username/password).
- Store credentials encrypted at rest (Postgres + AES‑GCM with master key from env).
- Attach service connections to repositories or org scope.
- Pipelines can request a service connection by name, injected as env vars.
- REST API for CRUD operations.

### Out of Scope (MVP)
- Advanced providers (Azure, GCP, Slack, GitHub apps).
- Rotation and expiration policies.
- Scoped secrets per environment (later).
- Audit logs of usage.
- UI for secret entry (API only in MVP).

---

## Personas
- **Platform Engineer**: Defines service connections (e.g., AWS creds).
- **Developer**: Uses pre‑defined connections in build/release templates.

---

## Architecture (Local‑First)
- Connections stored in Postgres encrypted column.
- Master key provided via env (`SERVICE_CONN_KEY`).
- Runner (Epic 6) fetches connection, decrypts, injects into container as env vars at job start.
- Local dev: `.env` loads master key for encryption.

---

## Data Model (SQL)
- **service_connections**(id uuid PK, org_id, name unique, type ENUM('generic','aws','docker'), config_encrypted bytea, created_by uuid, created_at)
- **repo_service_connections**(repo_id, connection_id, created_at)

Indexes: org_id+name unique.

---

## REST API (MVP)
Base path: `/api/v1`

- `POST /service-connections` → { name, type, config {..} }
- `GET /service-connections` → list connections (name, type; no secrets).
- `GET /service-connections/{id}` → details (no secret values).
- `DELETE /service-connections/{id}`

Repo attach:
- `POST /repos/{repo}/service-connections` → { connectionId }
- `GET /repos/{repo}/service-connections`

---

## Acceptance Criteria
- Can create service connection with credentials.
- Pipeline run requests connection, creds injected as env vars.
- Unauthorized users cannot read secret values (only admins can create/delete connections).
- Repo can only use attached connections.

---

## Test Plan
- Unit: encrypt/decrypt logic, env var injection.
- Integration: create AWS connection, run build template requiring it, creds visible inside container.
- E2E: unauthorized request for connection fails with 403.

---

## Config (env)
```
SERVICE_CONN_KEY=local_dev_master_key_32bytes
```

---

## Future (Post‑MVP)
- Additional providers (Azure, GCP, Slack, GitHub apps).
- Secret rotation and auto‑refresh.
- Scoped per‑environment secrets.
- Usage audit logs.
- UI for managing service connections.
