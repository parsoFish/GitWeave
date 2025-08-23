# GitWeave — Epic 4: Work Item Backlog (Local‑First MVP)

**Goal:** Provide a minimal backlog system directly tied to repositories and commits. Must run fully locally with no external integrations. Serves as the basis for issue tracking and DORA lead time metrics.

---

## Scope (MVP)
- Create, update, close basic work items (issues).
- Fields: id, title, description, state (open/closed), labels (tags), created_by, created_at.
- Link commits to work items via commit message syntax (`#<id>`).
- REST API for CRUD operations.
- Store in Postgres, simple schema.

### Out of Scope (MVP)
- Rich text/Markdown rendering (store plain text only).
- Nested work items or sub‑tasks.
- Epics/milestones/roadmaps.
- Advanced workflows (custom states, transitions).
- UI board view (API only at MVP).
- External integrations (Jira, ADO, GitHub Issues).

---

## Personas
- **Developer**: Creates/updates issues, closes them via commits or API.
- **PM/Lead**: Lists and filters issues to track backlog.

---

## Architecture (Local‑First)
- Extend `app` service with `work‑svc` API endpoints.
- Work items persisted in Postgres.
- Commit webhook (from git push event) scans commit messages; links issues automatically.
- Local dev: API only, UI to come later.

---

## Data Model (SQL)
- **work_items**(id serial PK, org_id, repo_id, title, description text, state ENUM('open','closed'), labels text[], created_by uuid, created_at, closed_at)
- **work_item_links**(work_item_id, commit_sha, repo_id, created_at)

Indexes: repo_id+id unique; commit_sha indexed.

---

## REST API (MVP)
Base path: `/api/v1`

- `POST /repos/{repo}/work-items` → { title, description, labels[] }
- `GET /repos/{repo}/work-items` → list, with optional filters (state, labels).
- `GET /repos/{repo}/work-items/{id}` → details.
- `PATCH /repos/{repo}/work-items/{id}` → update (title, description, labels, state).
- `DELETE /repos/{repo}/work-items/{id}` → soft delete (optional).

Commit linking:
- On push, service parses commit messages for `#<id>` and inserts into `work_item_links`.
- Closing keywords: “fixes #<id>”, “closes #<id>” ⇒ sets state=closed.

---

## Acceptance Criteria
- Can create an issue via API, retrieve it, update it, close it.
- Commit with “fixes #1” in repo closes issue #1 on push.
- List endpoint shows issues by state and labels.
- Work items linked to commits visible via API.

---

## Test Plan
- Unit: parser for commit messages, label array validator.
- Integration: create/update/close work item, push commit referencing item.
- E2E: push commit with “fixes #1” closes issue; list shows closed.

---

## Config (env)
_No new config for MVP._

---

## Future (Post‑MVP)
- Rich text/Markdown fields.
- Epics, milestones, sprints.
- Kanban board UI.
- Workflow customization (custom states, transitions).
- External integrations (Jira import/export, Slack notifications).
- Metrics dashboards for backlog trends.
