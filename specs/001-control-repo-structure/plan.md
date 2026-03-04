# Implementation Plan: Control Repository Structure

**Branch**: `001-control-repo-structure` | **Date**: 2025-12-13 | **Spec**: [specs/001-control-repo-structure/spec.md](../001-control-repo-structure/spec.md)
**Input**: Feature specification from `/specs/001-control-repo-structure/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

This feature establishes the foundational directory structure for the GitWeave Control Repository. It defines the layout for `modules/` (templates), `config/` (overlays), `infra/` (Terraform bootstrap), and `metrics/` (observability). It also includes the initial GitHub Actions workflows (`gitweave-apply.yaml`, `gitweave-infra.yaml`) and a `README.md` detailing the bootstrap process.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: HCL (Terraform), YAML, Python 3.11+ (Metrics Service), Bash
**Primary Dependencies**: GitHub Actions, Terraform CLI, Python (requests, prometheus_client)
**Storage**: Git Repository (Filesystem), Remote State (User Configured)
**Testing**: Directory structure verification, Workflow dry-runs
**Target Platform**: GitHub Organization
**Project Type**: Monorepo / Control Repository
**Performance Goals**: N/A (Structure only)
**Constraints**: Must be compatible with GitHub Actions runners
**Scale/Scope**: Single Control Repo per Organization

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Control Repo Centricity**: ✅ Compliant. This feature creates the single core repository structure.
- **II. Provider-Native First**: ✅ Compliant. Relies on GitHub Actions and GitHub hosting.
- **III. Platform as Code & Local Reproducibility**: ✅ Compliant. Sets up `config/` and `infra/` for declarative management.
- **IV. Composable Modules**: ✅ Compliant. Creates `modules/` directory.
- **V. Observability via Standards**: ✅ Compliant. Creates `metrics/` directory for the observer.
- **VI. Integrated Work Management**: N/A (Enabler).
- **VII. Secure Supply Chain**: N/A (Enabler).

## Project Structure

### Documentation (this feature)

```text
specs/001-control-repo-structure/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
.
├── .github/
│   └── workflows/
│       ├── gitweave-apply.yaml
│       └── gitweave-infra.yaml
├── config/
│   └── .gitkeep
├── infra/
│   └── .gitkeep
├── metrics/
│   └── .gitkeep
├── modules/
│   └── .gitkeep
└── README.md
```

**Structure Decision**: Monorepo structure as defined in the Feature Spec.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

N/A

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
