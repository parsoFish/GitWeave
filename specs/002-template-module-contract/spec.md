# Feature Specification: Template Module Contract

**Feature Branch**: `002-template-module-contract`  
**Created**: 2025-12-12  
**Status**: Draft  
**Input**: User description: "Define the Template Module Contract. A module is a directory in modules/ containing a copier.yaml metadata file and a content/ folder (files to copy or the actual templated component). It must support variable substitution (e.g. {{project_name}}) and lifecycle management (updates via PRs). We will use Copier as the engine to support composition and non-destructive updates. Versioning will follow CalVer (YYYYMMDD.Patch)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Module Metadata (Priority: P1)

As a Platform Engineer, I want to define a module's inputs and metadata in a standard file (e.g., `copier.yaml`), so that the system knows what variables to ask for when generating or updating a repo.

**Why this priority**: Metadata is the contract between the template and the consumer.

**Independent Test**: Can be tested by creating a valid `copier.yaml` and verifying a parser can read the input definitions.

**Acceptance Scenarios**:

1. **Given** a module directory `modules/example-mod`, **When** I add a `copier.yaml` with `inputs: [project_name]`, **Then** the system recognizes `project_name` as a required variable.
2. **Given** a module with missing metadata, **When** I try to validate it, **Then** the system reports an error.

---

### User Story 2 - Template Content with Variable Substitution (Priority: P1)

As a Platform Engineer, I want to place source files in a `content/` (or root) directory and use Jinja2 syntax (e.g., `{{ project_name }}`), so that the generated code is customized for the target repository.

**Why this priority**: This is the core value proposition of templating.

**Independent Test**: Can be tested by rendering a simple file `README.md` containing `{{ project_name }}` and verifying the output contains the actual name.

**Acceptance Scenarios**:

1. **Given** a file `content/README.md` with text `# {{ project_name }}`, **When** I render the module with `project_name="MyRepo"`, **Then** the output file contains `# MyRepo`.
2. **Given** a file path `content/{{project_name}}.ts`, **When** I render the module, **Then** the output filename is substituted correctly (e.g., `MyRepo.ts`).

---

### User Story 3 - Composition of Multiple Modules (Priority: P2)

As a Platform Engineer, I want to apply multiple modules to a single repository (e.g., "Node.js Base" + "GitHub Actions CI"), so that I can compose features rather than maintaining monolithic templates.

**Why this priority**: Composition is a core principle (Constitution IV).

**Independent Test**: Can be tested by applying two distinct modules to the same output directory and verifying files from both exist.

**Acceptance Scenarios**:

1. **Given** Module A (creates `fileA`) and Module B (creates `fileB`), **When** I apply both to `output/`, **Then** `output/` contains both `fileA` and `fileB`.
2. **Given** Module A and Module B both define `README.md`, **When** I apply them, **Then** the system handles the conflict using Copier's native merge strategy (relying on `.copier-answers.yml` to resolve diffs).

### User Story 4 - Update Module via Pull Request (Priority: P2)

As a Platform Engineer, I want to update a repository's applied modules non-destructively, so that I can propose changes (e.g., "Upgrade to Node 20") via a Pull Request rather than forcing an overwrite.

**Why this priority**: Safety and reviewability are critical for "Day 2" operations.

**Independent Test**: Apply version 1 of a module, then apply version 2, and verify the diff is generated without destroying user customizations.

**Acceptance Scenarios**:

1. **Given** a repo generated from `v1` of a module, **When** I apply `v2` of the module, **Then** the system generates a diff of the changes.
2. **Given** a user has modified a file that the template also modifies, **When** I update, **Then** the system attempts a merge (or flags a conflict) rather than blindly overwriting.

---

### User Story 5 - Propagate Updates from Control Repo (Priority: P2)

As a Platform Engineer, I want changes to modules in the Control Repo to trigger update Pull Requests on all consuming repositories, so that I can roll out standards across the organization efficiently.

**Why this priority**: Enables "Platform Push" updates, keeping the fleet consistent.

**Independent Test**: Update a module in the Control Repo, tag a new version, and verify that a consuming repo receives a PR with the update.

**Acceptance Scenarios**:

1. **Given** a module `lang-node` used by `repo-a`, **When** I update `lang-node` in the Control Repo and tag a new version (e.g., `20251212.1`), **Then** `repo-a` receives a Pull Request to upgrade to `20251212.1`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each module MUST reside in its own subdirectory under `modules/` (e.g., `modules/lang-node`).
- **FR-002**: Each module MUST contain a metadata file (standardizing on `copier.yaml` for lifecycle management support) defining inputs and default values.
- **FR-003**: The module content MUST support Jinja2 templating syntax for both file content and file paths.
- **FR-004**: The system MUST support rendering a module to a target directory, substituting variables defined in the metadata.
- **FR-005**: The system MUST support applying multiple modules sequentially to the same target directory (composition).
- **FR-006**: The system MUST support updating an already-applied module, preserving user changes where possible (reconciliation).
- **FR-007**: The system MUST support versioning of modules using CalVer (YYYYMMDD.Patch) tags on the Control Repo.

### Key Entities

- **TemplateModule**: A directory containing `copier.yaml` and template content.
- **TemplateInput**: A variable defined in `copier.yaml` (key, default value, type).
- **RenderContext**: The map of variable names to actual values used during generation.

### Assumptions

- We will use **Copier** as the underlying engine because it natively supports lifecycle management (updates) and composition better than Cookiecutter.
- Updates will be delivered via Pull Requests (implementation detail for the Apply workflow, but supported by the engine's diff capability).
- Versioning will follow **CalVer** (YYYYMMDD.Patch) to simplify currency calculations.
- Conflict resolution relies on **Copier's native 3-way merge** capabilities.
