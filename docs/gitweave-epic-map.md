# GitWeave Epic Map

This document maps epics to domain objects, dependencies, and success criteria for the GitWeave platform.

| Epic | Primary domain objects | Depends on | Personas | “Done” / success signals |
|---|---|---|---|---|
| 1) Authentication & Identity | `Authentication`, `Users` | — | Org Admin, User | SSO works; users can sign in/out; basic profile/2FA |
| 2) Teams & Permissions | `Teams`, `Permissions`, (role/Scope) | (1) | Org Admin, Team Lead | Role matrix enforceable at org/project/repo/pipeline |
| 3) Repositories Core | `Repositories`, `BranchingStrategy` | (1)(2) | Dev, Maintainer | Create/import/mirror; branch rules attach cleanly |
| 4) Work Item Backlog | `WorkItem`, links to `Repository`/commit | (1)(2)(3) | Dev, PM | Create/assign/close; links to commits and releases |
| 5) Platform Core: Opinionated Templates ⭐ | `BuildTemplate`, `TestTemplate`, `ReleaseTemplate`, `BranchingStrategy` | (2)(3) | DevEx/Platform, Dev | One‑click attach template; versioned templates; overridable inputs |
| 6) Pipeline Runner & Interpreter | `Runner`, `PipelineInterpreter`, `Job`, `Log` | (2)(5) | DevEx/Platform | Register runners; execute templates; collect logs/artifacts |
| 7) Build Module | `Build`, `Artifact` (pointer) | (3)(5)(6) | Dev | Build from repo via template; publish artifact |
| 8) Test Module | `TestRun`, `Report` | (5)(6)(7) | Dev, QA | Runs under build; surfaces pass/fail + coverage |
| 9) Release Module | `Release`, `Deployment` | (2)(5)(6)(7)(10) | Dev, Release Mgr | Promote artifact; record approvals; traceability to commit/work items |
| 10) Artifact Storage & Package Mgmt | `ArtifactStore`, `Package` | (7) | Dev, Platform | Immutable storage; retention rules; provenance |
| 11) Service Connections | `ServiceConnection` | (2) | Platform Admin | Securely reference cloud/SaaS creds from templates |
| 12) Built‑in DORA Metrics ⭐ | `DoraSnapshot`, sources: `Repo`, `PR/Commit*`, `Pipeline`, `Release` | (3)(6)(7)(8)(9) | Exec, DevEx | DF/Lead time/MTTR/CFR auto‑computed from native data |

---

⭐ = Differentiator epics for GitWeave
