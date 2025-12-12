# Feature Specification: Overlay Config Schema

**Feature Branch**: `003-overlay-config-schema`  
**Created**: 2025-12-12  
**Status**: Draft  
**Input**: User description: "Define the Overlay Config Schema. This is the YAML schema for files in config/repos/. It must map a repository (owner/name) to a list of applied modules (with their input values and optional version pins) and define environment-specific settings. Terraform will be the unified orchestrator, using this config to provision both infrastructure (GitHub Provider) and content (Copier)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Repository Identity & Modules (Priority: P1)

As a Platform Engineer, I want to create a YAML file in `config/repos/` that defines a repository's identity (`owner/name`) and a list of modules to apply, so that I can compose the repository from templates.

**Why this priority**: This is the primary function of the overlay system.

**Independent Test**: Can be tested by validating a sample YAML file against a JSON schema validator.

**Acceptance Scenarios**:

1. **Given** a file `config/repos/my-app.yaml`, **When** I define `repository: my-org/my-app` and `modules: [{name: lang-node, inputs: {version: 18}}]`, **Then** the schema validator accepts it as valid.
2. **Given** a file missing the `repository` field, **When** I validate it, **Then** the validator rejects it.

---

### User Story 2 - Define Flexible Environments (Priority: P1)

As a Platform Engineer, I want to define an arbitrary list of environments (e.g., `dev`, `uat`, `prod`, or `feature-*`) with specific settings (protection rules, secrets), so that I can support diverse deployment workflows like ephemeral environments.

**Why this priority**: Supporting complex workflows (ephemeral, feature stacks) is a key differentiator.

**Independent Test**: Can be tested by defining a regex-based environment pattern (e.g., `feature/*`) in the YAML and verifying the schema accepts it.

**Acceptance Scenarios**:

1. **Given** an environment definition named `prod`, **When** I specify `protection_rules: { required_reviewers: 2 }`, **Then** the schema accepts it.
2. **Given** an environment definition named `feature-stacks`, **When** I specify `pattern: feature/*` and `lifecycle: ephemeral`, **Then** the schema accepts it.

---

### User Story 3 - Map Config to Unified Provisioning (Priority: P2)

As a Platform Engineer, I want the overlay config to map cleanly to a unified Terraform variable structure, so that I can use Terraform to orchestrate both the infrastructure (GitHub Repo) and the content generation (Copier execution).

**Why this priority**: Terraform is the single orchestrator for the platform (Constitution III).

**Independent Test**: Can be tested by generating a `tfvars.json` file from the YAML config and verifying it contains both the infrastructure settings (teams, protection) and the module definitions (Copier inputs).

**Acceptance Scenarios**:

1. **Given** a valid overlay config with `modules: [{name: lang-node}]`, **When** I run the transformation, **Then** the output JSON includes a structure compatible with a Terraform module that accepts repository definitions and their associated templates.
2. **Given** this output, **When** Terraform runs, **Then** it has all the data needed to provision the repo AND trigger the content generation.

## Success Criteria *(mandatory)*

- **Automated Validation**: 100% of configuration files can be validated against the schema without manual review.
- **Zero-Touch Provisioning**: The schema supports all necessary properties to provision a repository and its environments via Terraform without manual intervention.
- **Extensibility**: New module definitions can be added to the schema without breaking existing repository configurations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST define a JSON Schema for files in `config/repos/*.yaml`.
- **FR-002**: The schema MUST require a `repository` field (string, format `owner/name`).
- **FR-003**: The schema MUST support a `modules` list, where each item has a `name` (string), optional `inputs` (key-value map), and optional `version` (string, Git ref/tag) to support pinned dependencies.
- **FR-004**: The schema MUST support an `environments` map or list, allowing definitions for standard (static) and dynamic (pattern-based) environments.
- **FR-005**: Environment definitions MUST support configuring `protection_rules` (reviewers, checks) and `secrets` (map of keys to values or references), which map to `github_actions_secret` resources in Terraform.
- **FR-006**: The schema structure MUST be compatible with transformation into a unified Terraform variable structure that supports both infrastructure provisioning (GitHub Provider) and content generation (Copier orchestration).

### Key Entities

- **OverlayConfig**: The top-level configuration object for a repository.
- **ModuleConfig**: Configuration for a specific applied template module.
- **EnvironmentConfig**: Configuration for a deployment environment (static or dynamic).

### Assumptions

- The GitHub Terraform Provider supports managing Environments and Branch Protection rules.
- **Terraform will act as the orchestrator**, responsible for both provisioning the repository infrastructure and triggering the content generation (Copier) process based on the config.
- Dynamic environments (e.g., `feature/*`) might require a separate automation (Actions) to provision on-the-fly, but the *configuration* for them lives here.
