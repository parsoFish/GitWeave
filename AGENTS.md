# GitWeave — Agent Instructions

## What this is

GitWeave is a single "control" repository that declares the standard for a GitHub organisation — settings, teams, policy and modules — and applies it through the GitHub API.

**Tech:** Python, GitHub Actions, the GitHub API. The `gw` CLI is planned, not yet built. **Tests:** pytest. **Licence:** AGPL-3.0-or-later with a contributor licence agreement.

## Commands

**Quality gate (credential-free):**
```bash
python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py --deselect tests/test_structure.py::TestRepoStructure::test_bootstrap_script_exits_zero
```

**CI gate:**
```bash
python3 -m pytest tests/test_structure.py tests/test_overlay_schema.py tests/test_copier_schema.py tests/test_copier_schema_ci.py
yamllint .github/workflows/
```

## Planning & history

- Planning input: `roadmap.md`. Current phase: **MVP greenfield scenario**.
- Initiative demo evidence: `history/<initiative-id>/demo/`.

## Commits

Conventional commits (`feat|fix|refactor|test|docs|chore|perf|ci`).

## Constitution

### I. Control Repo Centricity — amended

All behaviour, configuration and templates drive from this repository. The repository holds the **standard** — declared org settings, teams, policy and modules; the GitHub API holds the **instances**. Driving behaviour does not require holding every instance.

### II. Provider-Native First

Leverage GitHub for hosting, CI (Actions), and Identity. Do not re-implement Git hosting or pipeline runners.

### III. Platform as Code & Local Reproducibility — amended

Organisation behaviour is declared as configuration in this repository and applied through the GitHub API by the `gw` CLI (`gw plan`, `gw apply`, `gw reset`). There is no Terraform and no state file: `gw plan` diffs the declaration against the live organisation, and runs as a credential-free dry run against a recorded fixture.

**Why no desired-state tool.** Repositories change constantly in content, and much of an org is self-service. A state file held in this repository makes every such change a control-repo pull request — the platform team either grants auto-close exceptions or drowns in PRs before any apply — and drifts the moment a team acts on its own. Therefore: the repository declares the standard, the API is the truth, and anything a team can change for itself is applied directly with policy checked at the point of request.

### IV. Composable Modules (Opinionated Templates)

Template modules (skeletons, workflows, infra) live inside the control repo for discoverability and reuse. Modules MUST be versioned and composable.

### V. Observability via Standards — amended

DORA metrics are computed **GitHub-natively** — from the provider's API on a schedule — and published in a Prometheus/OpenTelemetry-compatible form. No hosted service, no database: an adopter inherits nothing to operate.

### VI. Integrated Work Management — amended

Work is tracked in GitHub Issues and Projects where a team chooses to. DORA lead time is measured commit-to-deploy from the provider API; it does not depend on Issue linking.

### VII. Secure Supply Chain

Use **GitHub Packages** for artifact storage and **GitHub Secrets / OIDC** for service connections. No custom artifact stores or credential managers.

## Non-Goals

- No competing CI runner (GitHub Actions is available)
- No bare git hosting (no `/data/repos`)
- No separate authentication surface (use GitHub IDP)
- No control-repo pull request in the path of a self-service change
- No Terraform or other state-file desired-state tool

## Untouchables

- No agent applies anything to a live organisation except the throwaway org named in `secrets.env`, and only to resources carrying forge's resource prefix.
- `LICENSE` and the CLA text change only by the operator's hand.

<!-- forge:composed-instruction-seeds: forge-managed-project -->
