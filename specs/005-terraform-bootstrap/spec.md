# Feature Specification: Terraform Bootstrap

**Feature Branch**: `005-terraform-bootstrap`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Defines the Infra. The baseline Terraform to manage the GitHub Org itself (Teams, Branch Protection Rules). Legacy Context: Relates to 'Epic 2: Teams' & 'Epic 3: Repos'."

## Clarifications

### Session 2025-12-13
- Q: How should Teams and Memberships be defined? → A: **Data-Driven (YAML)**. Terraform reads `config/teams.yaml` to create teams/memberships.
- Q: How should branch protection rules be applied (Global vs Opt-in)? → A: **Global Default with Exemptions**. Rules apply globally by default, but support:
    - Explicit exemptions (repos to ignore).
    - A "Global Enforcement" toggle (if disabled, rules only apply to `gitweave-managed` repos).
    - Per-repo overrides (additive or replacement policies).
- Q: How should existing resources be imported? → A: **Automated Helper Script**. A script will scan the Org and generate Terraform import blocks.
- Q: How should the system handle importing repositories that are not yet formatted for Copier (legacy)? → A: **Graceful but Enforced Adoption**. The import process allows initial Terraform management (settings/teams) without Copier compliance, BUT triggers a mandatory "Onboarding PR" that applies the necessary Copier metadata and structure to bring the repo into compliance.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manage Core Teams (Priority: P1)

As an Org Admin, I want to define our core teams (e.g., `platform-engineers`, `developers`) in code, so that membership and permissions are audited and versioned.

**Why this priority**: Foundation for RBAC.

**Independent Test**: Apply the Terraform config and verify the teams exist in the GitHub UI with the correct members.

**Acceptance Scenarios**:

1. **Given** a Terraform definition for team `platform-engineers`, **When** I run `terraform apply`, **Then** the team is created in the GitHub Org.
2. **Given** a change in the member list in code, **When** I apply, **Then** the GitHub team membership is updated to match.

---

### User Story 2 - Enforce Global Branch Protection (Priority: P1)

As a Security Engineer, I want to enforce baseline branch protection rules (e.g., "Require PR reviews") on all repositories, while retaining the flexibility to exempt legacy projects or apply stricter rules to critical repos.

**Why this priority**: Security compliance with operational flexibility.

**Independent Test**:
1. Create a repo. Verify it gets the rules.
2. Add it to the exemption list. Verify rules are removed/ignored.
3. Toggle the "Global Enforcement" flag off. Verify only repos with the topic get the rules.

**Acceptance Scenarios**:

1. **Given** the global enforcement is ON, **When** I apply, **Then** all repos (except exemptions) have the baseline rules.
2. **Given** a repository in the exemption list, **When** I apply, **Then** the baseline rules are NOT applied to it.
3. **Given** the global enforcement is OFF, **When** I apply, **Then** only repositories with the `gitweave-managed` topic receive the rules.

---

### User Story 3 - Bootstrap the Control Repo (Priority: P2)

As a Platform Engineer, I want the Control Repo to manage its own configuration (e.g., its own branch protection), so that the platform itself is immutable without code changes.

**Why this priority**: "Eat your own dogfood" / Platform as Code.

**Independent Test**: Change a setting for the Control Repo in Terraform, apply, and verify the Control Repo's settings change.

**Acceptance Scenarios**:

1. **Given** the Control Repo's definition in Terraform, **When** I apply, **Then** the Control Repo's settings (description, topics, protection) are updated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST use Terraform to manage GitHub Organization resources.
- **FR-002**: The system MUST support defining Teams and Team Memberships.
- **FR-003**: The system MUST support defining Branch Protection Rules that can be applied globally OR to a specific subset of repositories.
- **FR-004**: The system MUST allow importing existing resources (brownfield support) to bring them under management.
- **FR-005**: The system MUST store Terraform State securely (e.g., in an S3 bucket or Terraform Cloud), NOT locally.
- **FR-006**: The system MUST support an "Exemption List" to exclude specific repositories from global policies.
- **FR-007**: The system MUST provide a configuration flag to toggle between "Enforce on All Repositories" and "Enforce on Managed Repositories Only".
- **FR-008**: The system MUST allow individual repositories to override or extend the baseline branch protection rules.
- **FR-009**: The system MUST provide an automated script (e.g., `scripts/import-org.sh`) to scan the GitHub Organization and generate Terraform import blocks for existing resources.
- **FR-010**: The import process MUST support "Legacy Adoption" by first bringing the repo under Terraform management, and then immediately generating an "Onboarding Pull Request" to apply the Copier template structure, ensuring eventual compliance.

### Key Entities

- **OrgConfig**: The baseline configuration for the Organization.
- **TeamDefinition**: Definition of a GitHub Team and its members.
- **ProtectionRule**: A reusable branch protection policy.

### Assumptions

- We have a valid GitHub PAT or App Installation Token with `admin:org` permissions.
- We have a location to store the Terraform State (e.g., AWS S3 + DynamoDB, or Azure Blob Storage).
- The "Overlay Config" (Feature 003) will eventually feed into this, but this feature (005) establishes the *baseline* infrastructure that the Overlay Config builds upon.
