<!--
Sync Impact Report:
- Version change: 1.1.0 (Refined with Legacy Features)
- Modified Principles:
  - III. Platform as Code (Added Local Reproducibility)
  - IV. Composable Modules (Explicitly linked to Opinionated Templates)
- Added Principles:
  - VI. Integrated Work Management (Maps Legacy Work Items to GitHub Issues)
  - VII. Secure Supply Chain (Maps Legacy Artifacts/Connections to GitHub Native)
- Governance:
  - Added GitHub Issues/Projects as standard for work tracking.
  - Added GitHub Packages as standard for artifact storage.
- Templates requiring updates: ✅ None
-->

# GitWeave Constitution

## Core Principles

### I. Control Repo Centricity
All behavior, configuration, and templates MUST drive from a single core repository. We do not build heavy standalone platforms; we overlay the provider.

### II. Provider-Native First
Leverage GitHub for hosting, CI (Actions), and Identity. Do not re-implement Git hosting or pipeline runners.

### III. Platform as Code & Local Reproducibility
Express all organization behavior via configuration, Terraform, and lightweight overlays. Avoid "always-on" services unless the outcome cannot be achieved via Actions + Terraform.
**Constraint**: CLI tooling MUST support local dry-runs (e.g., `gw:plan`) to ensure developer confidence before applying changes.

### IV. Composable Modules (Opinionated Templates)
Template modules (skeletons, workflows, infra) live inside the control repo for discoverability and reuse. These modules MUST be versioned and composable to provide an "Opinionated Template" experience (formerly Epic 5).

### V. Observability via Standards
Expose DORA metrics in Prometheus/OpenTelemetry-compatible formats rather than proprietary stores.

### VI. Integrated Work Management
Use **GitHub Issues and Projects** for all work tracking (formerly Epic 4). Do not build custom issue trackers.
**Requirement**: Commits and PRs MUST be linked to Issues to enable DORA lead-time calculations.

### VII. Secure Supply Chain
Use **GitHub Packages** for artifact storage (formerly Epic 10) and **GitHub Secrets / OIDC** for service connections (formerly Epic 11). Do not build custom artifact stores or credential managers.

## Non-Goals

*   **No Competing CI Runner**: We will not build a competing pipeline runner when GitHub Actions is available.
*   **No Bare Git Hosting**: We will not host bare git repositories manually (no `/data/repos`).
*   **No Separate Auth**: We will not introduce a separate authentication surface; use GitHub IDP.

## Governance

*   **Primary Deployment Unit**: The Control Repository is the single source of truth.
*   **Infrastructure Provisioning**: Terraform is the standard for all infrastructure provisioning.
*   **Orchestration**: GitHub Actions is the standard for all orchestration and automation workflows.
*   **Work Tracking**: GitHub Issues & Projects are the standard for backlog management.
*   **Artifacts**: GitHub Packages is the standard for build output storage.

**Version**: 1.1.0 | **Ratified**: 2025-12-10 | **Last Amended**: 2025-12-10
