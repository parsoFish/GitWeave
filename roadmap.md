# GitWeave roadmap

**North star:** One control repo weaves a GitHub org: declared standards applied through the API, self-service first, DORA from GitHub itself.

## Current phase — MVP: the greenfield scenario

GitWeave is a product for any GitHub organisation. The April 2026 build was a
spike: tests written first, about half the implementation built, then stopped.
This phase restarts from an honest core and delivers one scenario end to end.

**The MVP is a scenario, not a feature.** Exercised by user stories against a
throwaway organisation with a narrowly-scoped token:

1. **Bootstrap** — from an empty organisation, stand up teams, repositories, CI
   and DORA.
2. **Update** — overlays applied; a new team onboarded; teams applying their own
   changes self-service; a template-module update resolving as a three-way merge
   against those local changes.
3. **Reset** — everything created returns to scratch, idempotently, so the next
   run starts clean.

Self-service is first-class throughout: anything a team can change for itself is
applied through the API with policy checked at request time, never through a
pull request against this repository.

## Initiatives, in land order

| # | Initiative | Depends on |
|---|---|---|
| I1 | An honest baseline: archive April, prune to what is true, licence, one green gate | — |
| I2 | The apply engine: `gw plan` / `gw apply` / `gw reset` over the GitHub API for declared org settings, teams, repositories and blanket rulesets; Terraform removed; plan needs no credentials | I1 |
| I3 | Self-service: team requests applied directly through the API, policy and exceptions checked at request time, no control-repo PR | I2 |
| I4 | Modules that exist, and overlays that apply them | I3 |
| I5 | Three-way reconcile of module updates against team-local changes | I4 |
| I6 | GitHub-native DORA, and the scenario end to end, twice, identical | I2, I4 |

## Non-goals

- A hosted service of any kind — no metrics server, no database, no dashboard to operate.
- A competing CI runner, git host, credential manager or identity surface.
- Terraform, or any desired-state tool holding a state file. Repositories change constantly in content; a state file over them drifts by design.
- A control-repo pull request in the path of a self-service change.
- Brownfield adoption of an existing org — after the MVP, not in it.

## Retired from April

The April tree is preserved on the `archive/april-2026` branch. Retired from
`main`: the empty `modules/example-template`; the permanently-red
`python-service` and `terraform-module` module suites; the orphaned
webhook-signature and metrics-token specs; the brownfield tests whose
implementation never existed; the FastAPI + PostgreSQL DORA service; the
duplicated update-PR generation; SpecKit-era residue. The Terraform in `infra/`
and its workflows retire in I2, as `gw` takes over their blanket intent.
