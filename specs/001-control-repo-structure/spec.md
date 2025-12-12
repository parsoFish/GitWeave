# Feature Specification: Control Repository Structure

**Feature Branch**: `001-control-repo-structure`  
**Created**: 2025-12-10  
**Status**: Draft  
**Input**: User description: "Define the Control Repository structure. It must include a modules/ directory for templates, a config/ directory for overlays, an infra/ directory for Terraform bootstrap, and a GitHub Actions workflow to apply changes. It should also include a README.md explaining how to bootstrap a new org."

## Clarifications

### Session 2025-12-13
- Q: Should the platform code be split across multiple repos or consolidated? → A: **Monorepo (Single Repo)**. All platform code (`modules/`, `config/`, `infra/`) lives in one `gitweave-control` repo.
- Q: How should CI/CD workflows be structured? → A: **Separate Workflows**. `gitweave-infra.yaml` triggers on `infra/**` (Terraform), `gitweave-apply.yaml` triggers on `config/**` (Content).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bootstrap New Organization (Priority: P1)

As a Platform Engineer, I want to clone the control repository into a new GitHub organization and have a clear structure for adding templates and configuration, so that I can start managing the organization immediately.

**Why this priority**: This is the foundational structure required before any other feature can be built.

**Independent Test**: Can be tested by verifying the directory structure exists and the README provides clear bootstrap instructions.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repo, **When** I inspect the root directory, **Then** I see `modules/`, `config/`, `infra/`, `metrics/`, `.github/workflows/`, and `README.md`.
2. **Given** the `README.md`, **When** I read the "Bootstrap" section, **Then** I see clear steps on how to configure the initial provider binding.

---

### User Story 2 - Add Template Module (Priority: P2)

As a Platform Engineer, I want a dedicated `modules/` directory where I can place reusable templates (e.g., `modules/lang-node`), so that I can keep my organization's standards DRY and discoverable.

**Why this priority**: Composable modules are a core principle of the constitution.

**Independent Test**: Can be tested by creating a dummy module in `modules/test-module` and verifying it doesn't conflict with other repo parts.

**Acceptance Scenarios**:

1. **Given** the `modules/` directory, **When** I create a new subdirectory `modules/my-template`, **Then** it is recognized as a valid location for a template module.

---

### User Story 3 - Define Overlay Configuration (Priority: P2)

As a Platform Engineer, I want a `config/` directory to store organization-wide and repository-specific configuration (overlays), so that I can manage policy and settings as code.

**Why this priority**: Platform-as-Code is a core principle.

**Independent Test**: Can be tested by adding a dummy config file in `config/` and verifying it is version-controlled.

**Acceptance Scenarios**:

1. **Given** the `config/` directory, **When** I add a configuration file (e.g., `config/example.yaml`), **Then** it is stored safely in the repo.

---

### User Story 4 - Apply Changes Workflow (Priority: P3)

As a Platform Engineer, I want a GitHub Actions workflow skeleton (`.github/workflows/gitweave-apply.yaml`) that triggers on changes to `config/`, so that the platform automatically reconciles state.

**Why this priority**: Automation via Actions is a core governance rule.

**Independent Test**: Can be tested by triggering the workflow manually or via push (even if it's a no-op initially).

**Acceptance Scenarios**:

1. **Given** a change to `config/`, **When** I push to main, **Then** the `gitweave-apply` workflow is triggered.

---

### User Story 5 - Infrastructure Directory (Priority: P2)

As a Platform Engineer, I want a dedicated `infra/` directory to store the Terraform configuration for the organization itself (e.g., teams, branch protection), so that the platform infrastructure is versioned and deployable via GitHub Actions.

**Why this priority**: Required to support Feature 005 (Terraform Bootstrap) and the "Platform as Code" principle.

**Independent Test**: Verify that the `infra/` directory exists.

**Acceptance Scenarios**:

1. **Given** the control repo, **When** I look for the location to store Terraform bootstrap code, **Then** I find the `infra/` directory.

---

### User Story 6 - Metrics Server Directory (Priority: P2)

As a Platform Engineer, I want a dedicated `metrics/` directory to store the source code for the Metrics Observer service (Go/Python), so that the observability component is versioned alongside the platform configuration.

**Why this priority**: Required to support Feature 004 (Metrics Observer) and keeps the custom service code organized.

**Independent Test**: Verify that the `metrics/` directory exists.

**Acceptance Scenarios**:

1. **Given** the control repo, **When** I look for the location to store the Metrics Observer code, **Then** I find the `metrics/` directory.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST have a `modules/` directory at the root for storing Template Modules.
- **FR-002**: The repository MUST have a `config/` directory at the root for storing Overlay Configuration.
- **FR-003**: The repository MUST have a `.github/workflows/` directory containing a `gitweave-apply.yaml` workflow skeleton.
- **FR-004**: The `gitweave-apply.yaml` workflow MUST be configured to trigger on `push` to `main` (filtered to `config/**` paths) and `workflow_dispatch`.
- **FR-005**: The repository MUST have a `README.md` (updated from the current one) that explicitly documents the folder structure (`modules/`, `config/`) and the Bootstrap process.
- **FR-006**: The repository MUST have an `infra/` directory at the root for storing Terraform Bootstrap configuration.
- **FR-007**: The repository MUST have a `.github/workflows/gitweave-infra.yaml` workflow skeleton configured to trigger on `push` to `main` (filtered to `infra/**` paths) and `workflow_dispatch`.
- **FR-008**: The repository MUST have a `metrics/` directory at the root for storing the Metrics Observer source code.

### Key Entities

- **ControlRepo**: The physical directory structure on disk.
- **TemplateModule**: A subdirectory within `modules/`.
- **OverlayConfig**: A file within `config/`.
