# Feature Specification: Metrics Observer

**Feature Branch**: `004-metrics-observer`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Defines Observability. A containerized service that ingests GitHub Webhooks (Deployment, PRs) and exposes DORA metrics via a Prometheus endpoint. It must be stateless/lightweight (no heavy DB) and portable to any container runtime (K8s, Cloud Run, ECS)."

## Clarifications

### Session 2025-12-12
- Q: Should the service enforce HMAC signature verification for incoming webhooks? → A: **Yes, enforce HMAC verification** (requires `WEBHOOK_SECRET` env var).
- Q: Should the service support multiple repositories or be single-repo scoped? → A: **Multi-Repository (Centralized)**. The service handles events from multiple repos and adds a `repository` label to all metrics.
- Q: Should the service expose raw counters/histograms or pre-calculated DORA aggregates? → A: **Raw Counters & Histograms**. The service exposes primitives (e.g., `deployments_total`, `lead_time_seconds_bucket`) and relies on Prometheus/Grafana for DORA calculation.
- Q: How should the service handle missing data (e.g., commit timestamps) in webhooks? → A: **Fetch from GitHub API**. The service will query the GitHub API (using `GITHUB_TOKEN`) to retrieve missing details required for metrics (e.g., Lead Time).
- Q: Should the service support a generic Push API for pipelines? → A: **Yes, add a generic Push API (Hybrid)**. Support both GitHub Webhooks AND a generic `POST /api/event` endpoint for explicit pipeline pushes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Track Deployment Frequency (Priority: P1)

As a Platform Engineer, I want to track how often we deploy to production, so that I can measure our DORA Deployment Frequency metric.

**Why this priority**: Core DORA metric for velocity.

**Independent Test**: Trigger a deployment in a test repo and verify the metric counter increments.

**Acceptance Scenarios**:

1. **Given** a repository configured with the metrics observer, **When** a GitHub Deployment status changes to `success`, **Then** the `deployment_frequency` metric is incremented for that repository/environment.
2. **Given** a failed deployment, **When** the status is received, **Then** the `change_failure_rate` counter is updated (or failure count incremented).

---

### User Story 2 - Measure Lead Time for Changes (Priority: P1)

As a Platform Engineer, I want to measure the time from code commit to production deployment, so that I can track Lead Time for Changes.

**Why this priority**: Core DORA metric for velocity/efficiency.

**Independent Test**: Create a PR, merge it, deploy it, and verify the calculated duration is recorded.

**Acceptance Scenarios**:

1. **Given** a PR merged at T1 and deployed at T2, **When** the deployment succeeds, **Then** the system records `lead_time = T2 - T1`.

---

### User Story 3 - Expose Metrics Endpoint (Priority: P2)

As a Platform Engineer, I want to deploy a containerized service that exposes a `/metrics` endpoint, so that I can scrape DORA metrics using my existing Prometheus infrastructure without managing a complex database.

**Why this priority**: Adheres to "Observability" principle and "No Heavy Database" constraint.

**Independent Test**: Deploy the container locally, send a mock webhook, and `curl localhost:8080/metrics` to verify the counter increments.

**Acceptance Scenarios**:

1. **Given** the service is running, **When** I send a `deployment_status` webhook, **Then** the `dora_deployment_frequency` metric is updated in memory.
2. **Given** a Prometheus scraper, **When** it hits `/metrics`, **Then** it receives the current state of the metrics in OpenMetrics format.

---

### User Story 4 - Portable Deployment (Priority: P3)

As a Platform Engineer, I want clear documentation and examples for deploying this container to major providers (AWS, Azure, GCP, Kubernetes), so that I can run it regardless of my underlying infrastructure.

**Why this priority**: Portability is a key non-functional requirement.

**Independent Test**: Verify that a `Dockerfile` exists and builds successfully, and that `docs/deployment.md` covers at least one major cloud provider.

**Acceptance Scenarios**:

1. **Given** the repository, **When** I build the Docker image, **Then** it produces a runnable container.
2. **Given** the documentation, **When** I follow the steps for AWS/Azure, **Then** I have a running instance of the observer.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST be a standalone containerized application (e.g., Go/Rust/Python) capable of receiving HTTP Webhooks.
- **FR-002**: The system MUST ingest GitHub Webhook events for `deployment_status`, `pull_request`, and `push`.
- **FR-003**: The system MUST expose raw metric primitives (Counters, Histograms) to allow downstream calculation of DORA metrics. It MUST NOT perform complex time-window aggregation internally.
- **FR-004**: The system MUST expose a `/metrics` endpoint compatible with Prometheus scraping.
- **FR-005**: The system MUST be stateless (metrics reset on restart) OR support optional persistence to a volume/bucket if durability is required.
- **FR-006**: The system MUST validate the `X-Hub-Signature-256` header on all incoming webhooks using a configured `WEBHOOK_SECRET`.
- **FR-007**: The system MUST support ingesting events from multiple repositories and MUST tag all exposed metrics with a `repository` label to distinguish sources.
- **FR-008**: The system MUST be capable of querying the GitHub API (using a provided `GITHUB_TOKEN`) to enrich webhook events with missing data (e.g., fetching commit timestamps for Lead Time calculation).
- **FR-009**: The system MUST expose a generic `POST /api/event` endpoint to allow authenticated clients (e.g., CI/CD pipelines) to explicitly push metric events (e.g., deployment start/failure) that may not be captured by GitHub Webhooks.

### Key Entities

- **ObserverService**: The containerized application.
- **MetricRegistry**: The internal component holding the current metric values.
- **WebhookHandler**: The component that parses incoming GitHub events and validates HMAC signatures.
- **ApiHandler**: The component that validates and processes explicit events from the generic push API.

### Assumptions

- The user has a container runtime (K8s, ECS, Cloud Run) to host the service.
- The user has a Prometheus-compatible scraper to ingest the metrics.
- The `WEBHOOK_SECRET` is securely injected into the container environment.
- For the "No Heavy Database" constraint, we accept that metrics might be ephemeral (reset on restart) unless an external persistence layer (like a PVC or S3) is configured, but the *default* mode is lightweight.
