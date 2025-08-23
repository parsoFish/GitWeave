# GitWeave Domain Model (Mermaid)

> Primary entities and relationships aligned to the epic map.  
> Notes: Role assignments can target multiple scopes (Org/Project/Repo/Environment/Pipeline). Templates are versioned and executed by runners to produce artifacts and releases.

```mermaid
classDiagram
    %% ===== Identity & Access =====
    class Organization {
      +id: UUID
      +name: string
      +settings: json
    }
    class Project {
      +id: UUID
      +name: string
      +key: string
    }
    class Team {
      +id: UUID
      +name: string
    }
    class User {
      +id: UUID
      +email: string
      +name: string
      +mfaEnabled: bool
    }
    class RoleAssignment {
      +id: UUID
      +role: Role
      +scopeType: ScopeType  %% org|project|repo|environment|pipeline
      +scopeId: UUID
      +createdAt: datetime
    }
    class Role {
      <<enumeration>>
      Owner
      Maintainer
      Developer
      Reporter
      Guest
      PipelineReader
      ReleaseApprover
    }
    class ScopeType {
      <<enumeration>>
      org
      project
      repo
      environment
      pipeline
    }

    Organization "1" o-- "*" Project
    Organization "1" o-- "*" Team
    Organization "1" o-- "*" User
    Team "*" o-- "*" User : membership
    RoleAssignment "*" --> User
    RoleAssignment "*" --> Team
    RoleAssignment "*" --> Organization : scope (org)
    RoleAssignment "*" --> Project : scope (project)
    RoleAssignment "*" --> Repository : scope (repo)
    RoleAssignment "*" --> Environment : scope (env)
    RoleAssignment "*" --> PipelineTemplate : scope (pipeline)

    %% ===== Repos & Work =====
    class Repository {
      +id: UUID
      +name: string
      +defaultBranch: string
      +visibility: enum
    }
    class Branch {
      +name: string
      +protected: bool
      +rules: json
    }
    class Commit {
      +sha: string
      +author: string
      +timestamp: datetime
      +message: string
    }
    class WorkItem {
      +id: int
      +title: string
      +state: enum
      +labels: set
    }

    Project "1" o-- "*" Repository
    Project "1" o-- "*" WorkItem
    Repository "1" o-- "*" Branch
    Branch "1" o-- "*" Commit
    WorkItem "*" --> "*" Commit : links
    WorkItem "*" --> "*" Release : included in

    %% ===== Templates & Pipelines =====
    class PipelineTemplate {
      <<abstract>>
      +id: UUID
      +name: string
      +version: semver
      +inputs: schema
    }
    class BuildTemplate {
    }
    class TestTemplate {
    }
    class ReleaseTemplate {
    }
    PipelineTemplate <|-- BuildTemplate
    PipelineTemplate <|-- TestTemplate
    PipelineTemplate <|-- ReleaseTemplate

    class Runner {
      +id: UUID
      +labels: set
      +selfHosted: bool
      +status: enum
    }
    class PipelineRun {
      +id: UUID
      +status: enum
      +startedAt: datetime
      +endedAt: datetime
      +logsRef: uri
    }
    class Job {
      +name: string
      +status: enum
      +durationSec: int
    }
    class Log {
      +offset: int
      +chunk: text
    }

    Repository "1" o-- "*" PipelineRun : triggers
    PipelineTemplate "*" --> "*" PipelineRun : instantiated as
    PipelineRun "1" o-- "*" Job
    Job "1" o-- "*" Log
    Runner "*" --> "*" Job : executes

    %% ===== Artifacts, Packages, Releases =====
    class ArtifactStore {
      +id: UUID
      +kind: enum  %% container|generic|maven|npm|pypi
      +retentionPolicy: json
    }
    class Artifact {
      +id: UUID
      +name: string
      +digest: string
      +provenance: json
    }
    class Package {
      +name: string
      +version: string
      +manifest: json
    }
    class Release {
      +id: UUID
      +name: string
      +notes: markdown
      +createdAt: datetime
    }
    class Environment {
      +id: UUID
      +name: string  %% dev|stg|prod
      +gates: json
    }
    class Deployment {
      +id: UUID
      +status: enum
      +startedAt: datetime
      +endedAt: datetime
    }

    PipelineRun "*" --> "*" Artifact : produces
    Artifact "*" --> "1" ArtifactStore : stored in
    Release "*" --> "*" Deployment : contains
    Deployment "*" --> "1" Environment : targets
    Release "*" --> "*" Artifact : references
    Release "*" --> "1" Repository : originates from

    %% ===== Connections & Metrics =====
    class ServiceConnection {
      +id: UUID
      +type: enum  %% aws|gcp|azure|slack|webhook
      +scope: json
    }
    class DoraSnapshot {
      +id: UUID
      +timeWindow: daterange
      +deploymentFrequency: number
      +leadTimeMs: int
      +mttrMs: int
      +changeFailureRate: percentage
    }

    ServiceConnection "*" --> "*" PipelineRun : used by
    DoraSnapshot "*" --> "*" Project : aggregates
    DoraSnapshot "*" --> "*" Team : aggregates
    DoraSnapshot "*" --> "*" Repository : aggregates
    DoraSnapshot "*" --> "*" Deployment : derived from
```

---

## (Optional) Delivery Flow (Sequence)
A high-level depiction from commit to prod deploy and metrics.

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Repo as Repository
    participant Runner as Runner
    participant CI as PipelineRun
    participant Store as ArtifactStore
    participant Rel as Release
    participant Env as Environment
    participant DORA as Dora Metrics

    Dev->>Repo: Push commit
    Repo->>CI: Trigger Build/Test templates
    CI->>Runner: Schedule jobs (labels match)
    Runner-->>CI: Execute jobs + logs
    CI->>Store: Publish Artifact
    CI-->>Rel: Create Release (notes from commits/issues)
    Rel->>Env: Deploy to Staging (gates/checks)
    Env-->>Rel: Approve & Promote to Prod
    Rel-->>DORA: Emit deployment event
    DORA-->>Dev: Update DF/LeadTime/MTTR/CFR dashboards
```

