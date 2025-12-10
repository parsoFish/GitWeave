// GitWeave SpecKit: Core vision as a single control repo overlaying GitHub

export const GitWeaveGithubOverlayCoreSpec = {
  meta: {
    name: 'GitWeave Core (GitHub Overlay)',
    version: 1,
    status: 'draft',
    sources: ['docs/gitweave-epic-map.md', 'docs/gitweave-domain-model.md'],
  },

  vision: {
    summary:
      'GitWeave is a single "control" repository that configures and weaves together a GitHub organisation using in-repo modules, overlays, and provider-native tooling.',
    goals: [
      'Run GitWeave from one core repo cloned into a GitHub org.',
      'Leverage GitHub as the Git host, CI engine (Actions), and identity provider.',
      'Express platform behaviour as code: configuration, Terraform, and lightweight overlays instead of a heavy standalone platform.',
      'Provide an excellent greenfield bootstrap experience for new GitHub orgs while also being safe to apply onto existing orgs.',
    ],
    nonGoals: [
      'Do not re-implement Git hosting (no bare repos under /data/repos).',
      'Do not build a competing pipeline runner when GitHub Actions is available.',
      'Avoid unnecessary always-on services when the same outcome can be achieved via GitHub Actions + Terraform + configuration.',
    ],
  },

  coreConcepts: {
    ControlRepository: {
      description:
        'The GitWeave core repository itself. It contains specs, Terraform, overlay configuration, and optional app code. All GitWeave behaviour is driven from this repo.',
      responsibilities: [
        'Holds SpecKit specs that describe the organisation, projects, templates, and overlays.',
        'Defines Terraform modules and configuration for provisioning GitHub resources and any supporting cloud infra.',
        'Provides GitHub Actions workflows and/or CLI scripts to apply configuration to the target GitHub organisation.',
        'Tracks overlay configuration for each managed repository (which templates apply, environments, policies, etc.).',
      ],
    },

    TemplateModule: {
      description:
        'A composable module stored inside the control repo (e.g. under modules/) that can generate or modify repositories: code skeletons, workflow packs, policies, or infra snippets.',
      storage:
        'Modules live alongside the core code (for example modules/lang-node/, modules/workflows/ci-basic/, modules/infra/service/). They can be implemented with cookie-composer, a similar self-baked engine, or simple scriptable templates.',
      behaviour: [
        'Modules are combined to construct a new repository: e.g. choose a language starter pack + a workflow pack + optional infra pack.',
        'The same module can be reused across many repos, keeping opinions DRY and easy to evolve.',
        'Teams can add new modules or override existing ones by contributing to the control repo, without needing separate template repositories.',
      ],
    },

    ManagedRepository: {
      description:
        'A normal GitHub repository representing an application, library, or infra component that GitWeave manages via overlays.',
      fields: [
        'provider: fixed to github for this spec.',
        'owner: GitHub organisation or user.',
        'name: repository name.',
        'defaultBranch: main branch name.',
      ],
      notes: [
        'GitWeave never stores Git history; it only keeps references and configuration.',
        'Managed repositories may pre-exist, or be created by GitWeave automation (via Terraform or GitHub REST APIs).',
      ],
    },

    OverlayConfig: {
      description:
        'Configuration that describes how a ManagedRepository is wired into templates, workflows, environments, and metrics.',
      storageOptions: [
        'Central config in the control repo (e.g. config/repos/*.yaml).',
        'Optional mirrored config file within each managed repo under .gitweave/ for local visibility.',
      ],
      typicalFields: [
        'repositoryRef: owner/name.',
        'appliedModules: list of TemplateModule identifiers and versions used to construct or update this repo.',
        'environments: dev/stage/prod definitions (URLs, deployment workflows, gates).',
        'doraSettings: how to interpret GitHub events and workflows for this repo.',
      ],
    },

    EnvironmentConfig: {
      description:
        'A logical environment (dev, staging, prod, etc.) that GitWeave understands for deployment flows and metrics.',
      fields: [
        'name: dev | staging | prod | ...',
        'deploymentWorkflow: reference to a GitHub Actions workflow file and job.',
        'gates: optional checks (approvals, checks that must pass before promotion).',
      ],
    },

    GitProviderBinding: {
      description:
        'The binding between the control repo and a specific GitHub organisation or account.',
      implementationOptions: [
        'GitHub App installation used by Actions workflows in the control repo.',
        'Organisation-level PAT stored as an Actions secret (simplest for prototypes).',
      ],
    },

    InfraDefinition: {
      description:
        'Infrastructure-as-code definitions, primarily using Terraform, that the control repo publishes for teams to use.',
      responsibilities: [
        'Provision GitHub repositories, teams, and repository settings (safe org-level operations).',
        'Provide Terraform modules for application/cloud resources; application teams own terraform plan/apply.',
        'Offer opinionated but lightweight infra blueprints (for example simple storage buckets across major cloud providers) that organisations can extend or replace.',
      ],
    },

    MetricsAggregator: {
      description:
        'A lightweight aggregator component that receives signals from managed repositories and turns them into DORA metrics and higher-level insights.',
      implementationOptions: [
        'A small Dockerised service that exposes Prometheus/OpenTelemetry-compatible metrics and optionally persists summaries back into the control repo.',
        'GitHub Actions workflows that periodically pull events/metrics and either publish Prometheus-style metrics (e.g. via an exporter) or commit summarised results back into the control repo.',
      ],
      responsibilities: [
        'Ingest commit, deployment, and workflow-run data from GitHub for all ManagedRepositories.',
        'Compute DORA metrics per repo, team, and environment.',
        'Expose metrics in industry-standard formats (Prometheus / OpenTelemetry) so common backends like Prometheus + Grafana can be used without custom storage.',
      ],
    },
  },

  usageModes: {
    greenfieldOrg: {
      description:
        'Bootstrap a brand-new GitHub organisation using the control repo as the starting point.',
      flow: [
        'Clone the control repo into the new GitHub organisation.',
        'Configure provider binding (GitHub App or PAT) via a single config file and secrets.',
        'Run a bootstrap workflow (GitHub Action or CLI) that reads specs + Terraform and creates initial template modules and service repos.',
        'Developers start from curated templates and inherit standard workflows by default.',
      ],
    },
    existingOrgOverlay: {
      description:
        'Apply GitWeave onto an existing GitHub organisation with pre-existing repositories.',
      flow: [
        'Clone the control repo into the organisation.',
        'Register existing repositories by adding OverlayConfig entries pointing at owner/name.',
        'Run overlay workflows that add or update GitHub Actions workflows, branch protection, and Terraform-managed infra where safe.',
      ],
    },
  },

  automationModel: {
    principles: [
      'Prefer GitHub Actions for orchestration wherever possible.',
      'Use Terraform for external/system configuration (repos, cloud infra) rather than bespoke Node services.',
      'Keep optional Dockerised services minimal and focused on things that cannot be easily expressed as Actions or Terraform.',
    ],
    components: {
      githubActions: {
        description:
          'Workflows defined in the control repo that read specs/config and call Terraform, GitHub APIs, or other CLIs to apply changes.',
      },
      terraform: {
        description:
          'Terraform modules in the control repo that define GitHub org/repo settings and example cloud infra; GitWeave never directly deploys project infrastructure, it only ships templates.',
      },
      optionalDockerApp: {
        description:
          'A Dockerised application (potentially the existing app/ folder) that can offer richer UX or long-running features, but is not required for basic flows.',
        examples: [
          'Dashboard for DORA metrics aggregated from GitHub.',
          'Inspector service that periodically scans repos and updates overlay status.',
        ],
      },
      metricsAggregator: {
        description:
          'Concrete implementation of the MetricsAggregator concept: either a service or scheduled workflows that collect data from GitHub and update metrics state.',
      },
    },
  },

  doraMetrics: {
    description:
      'DORA metrics are computed from GitHub events and GitHub Actions workflow runs associated with ManagedRepositories and their environments.',
    dataSources: [
      'GitHub push events and commit metadata for lead time calculations.',
      'GitHub Actions workflows that perform deployments for deployment frequency and MTTR.',
      'Workflow failures tagged as deployment failures for change failure rate.',
    ],
    storage:
      'Metrics are aggregated by the MetricsAggregator and exposed via Prometheus/OpenTelemetry-compatible endpoints, with optional summarised snapshots written to a canonical location (e.g. data/dora/*.json) for GitWeave-specific dashboards.',
  },

  interfaces: {
    configurationFiles: {
      description:
        'YAML/JSON files in the control repo that define provider bindings, template modules, managed repositories, and overlays.',
      examples: [
        'config/providers/github.yaml: GitHub org binding and authentication mode.',
        'config/modules/*.yaml: catalogue of TemplateModule definitions and their parameters.',
        'config/repos/*.yaml: OverlayConfig per ManagedRepository.',
      ],
    },
    cliAndWorkflows: {
      description:
        'Simple CLI scripts and GitHub Actions workflows that read configuration and apply it.',
      examples: [
        'npm run gw:plan – dry-run of Terraform + GitHub changes.',
        'npm run gw:apply – apply overlays and Terraform changes.',
        'GitHub Actions workflow .github/workflows/gitweave-apply.yaml triggered on config changes.',
      ],
    },
    aiAssistants: {
      description:
        'Conventions and helper artefacts that make GitWeave-friendly repos and modules easy for Copilot and other agents to understand and extend.',
      examples: [
        'Machine-readable module metadata (inputs/outputs/constraints) so agents can safely compose modules when generating new repos.',
        'Curated prompt files and command palettes (e.g. under .github/copilot/ or .specify/) that guide agents through GitWeave-specific flows.',
        'Standardised repo layouts and naming that let agents reliably locate configs, workflows, and infra for a given service.',
      ],
    },
  },

  assumptionsAndDecisions: {
    assumptions: [
      'Primary provider is GitHub; other providers are future work.',
      'Users already authenticate to GitHub; GitWeave does not introduce a new login surface.',
      'Running via GitHub Actions is acceptable for most organisations; local CLI is a secondary entry point.',
    ],
    keyDecisions: [
      {
        id: 'gw-core-1',
        title: 'Single control repository is the primary deployment unit',
        rationale:
          'Keeps the system simple to adopt: clone one repo and configure. Avoids a separate always-on platform service unless strictly necessary.',
      },
      {
        id: 'gw-core-2',
        title: 'Template modules live inside the control repo',
        rationale:
          'Keeps everything discoverable from a single repository, makes it easy to mix-and-match language starters with workflow packs, and simplifies extension by contributors.',
      },
      {
        id: 'gw-core-3',
        title: 'Terraform is the preferred mechanism for provisioning',
        rationale:
          'Terraform is battle-tested for GitHub + cloud infra and aligns with “platform as code” better than custom Node glue.',
      },
      {
        id: 'gw-core-5',
        title: 'Prometheus-style metrics as the default contract',
        rationale:
          'Using Prometheus/OpenTelemetry-compatible metrics allows teams to plug in familiar backends like Prometheus and Grafana without GitWeave owning a bespoke time-series database.',
      },
      {
        id: 'gw-core-4',
        title: 'No separate auth platform by default',
        rationale:
          'GitHub already provides identity and access; keeping GitWeave as an overlay prevents duplicated auth flows and reduces operational burden.',
      },
    ],
  },
};
