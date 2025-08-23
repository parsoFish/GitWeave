# GitWeave — Epic 5: Platform Core (Opinionated Templates, Local‑First MVP)

**Goal:** Provide a centralized, opinionated system for defining build, test, and release templates that can be attached to repositories. Local‑first design: templates stored and executed within the local environment, enabling developers to adopt consistent CI/CD patterns without writing bespoke pipelines.

---

## Scope (MVP)
- Define and store versioned templates for build, test, and release (YAML/JSON).
- Parameters supported (e.g., language, runtime, image).
- Attach template(s) to a repository (metadata entry).
- Run templates via the pipeline runner (Epic 6).
- Simple update mechanism: repo can pin version or track “latest”.
- REST API to manage templates (CRUD).
- Templates executed locally, stored in Postgres.

### Out of Scope (MVP)
- UI editor for templates (API only at MVP).
- Template inheritance/extension.
- Cross‑org/global template sharing (single org only).
- Canary rollout/version migration (manual update only in MVP).
- Policy enforcement (mandatory templates by org admins).

---

## Personas
- **DevEx/Platform Engineer**: Creates templates, updates them, attaches them to repos.
- **Developer**: Uses attached templates; no need to write pipelines manually.

---

## Architecture (Local‑First)
- `template‑svc` within `app` container manages templates.
- Templates stored in Postgres and materialized to disk when executed.
- Runner (Epic 6) pulls template definition, expands params, and executes locally.
- Local dev: templates are API‑defined and stored directly.

---

## Data Model (SQL)
- **pipeline_templates**(id uuid PK, type ENUM('build','test','release'), name, version semver, inputs jsonb, body text, created_by uuid, created_at)
- **repo_templates**(repo_id, template_id, version semver, track_latest bool, attached_at)

Indexes: (name,type,version) unique; repo_id+template_id unique.

---

## REST API (MVP)
Base path: `/api/v1`

### Templates
- `POST /templates` → { type, name, version, inputs, body }
- `GET /templates?type=build` → list templates.
- `GET /templates/{id}` → template details.
- `PATCH /templates/{id}` → update (body, inputs).
- `DELETE /templates/{id}`

### Repo Attachments
- `POST /repos/{repo}/templates` → { templateId, version, trackLatest }
- `GET /repos/{repo}/templates`
- `DELETE /repos/{repo}/templates/{id}`

---

## Acceptance Criteria
- Can create a build/test/release template via API.
- Repo can attach template, run pipeline (Epic 6 executes).
- Templates can be updated; repos tracking “latest” see new behavior.
- Templates pinned to a version remain stable.

---

## Test Plan
- Unit: template parser, version comparator, param validator.
- Integration: create template, attach to repo, runner executes pipeline.
- E2E: update template, repo tracking latest picks up new version automatically.

---

## Config (env)
_No new config for MVP._

---

## Future (Post‑MVP)
- Template inheritance and composition.
- Canary rollout with automatic rollback if failure rate increases.
- Org‑wide enforced templates (e.g., mandatory security checks).
- Template UI with editor and validation.
- Policy sets (Golden Paths) that attach multiple templates at once.
