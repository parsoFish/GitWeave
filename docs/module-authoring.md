# Module Authoring Guide

This guide explains how to create, test, version, and publish a new GitWeave template module.
It is self-contained: a reviewer new to Copier can follow it from scratch and produce a working module.

## Table of Contents

1. [Module Directory Structure](#module-directory-structure)
2. [copier.yaml Reference](#copieryaml-reference)
3. [Jinja2 Templating](#jinja2-templating)
4. [Variable Types and Validation](#variable-types-and-validation)
5. [Module Composition and Inheritance](#module-composition-and-inheritance)
6. [Local Testing Workflow](#local-testing-workflow)
7. [CalVer Versioning Convention](#calver-versioning-convention)
8. [Publishing a Module Update](#publishing-a-module-update)
9. [Conflict Resolution Runbook](#conflict-resolution-runbook)

---

## Module Directory Structure

Each module lives under `modules/<name>/` in the control repository.

```
modules/
└── my_module/
    ├── copier.yaml          # Module metadata and variable definitions
    ├── README.md            # Human-readable description of the module
    └── content/             # Jinja2 template files that get rendered into the target repo
        ├── .github/
        │   └── workflows/
        │       └── ci.yaml.jinja
        └── README.md.jinja
```

**Conventions:**

- The directory name (`my_module`) becomes the canonical module identifier.
- All template files go inside `content/`. Non-template files (e.g. module README) sit alongside `copier.yaml`.
- Jinja2 templates use the `.jinja` file extension. Copier strips it during rendering.
- Nested directories inside `content/` are recreated verbatim in the target repository.

---

## copier.yaml Reference

`copier.yaml` is the control file for a Copier module. It declares metadata, input variables, and rendering options.

### Minimal Example

```yaml
_metadata:
  name: my_module
  version: "20240101.0"
  description: "Adds a standard CI workflow to a repository."

questions:
  project_name:
    type: str
    help: "The name of the project (used in workflow titles)."
    default: "my-project"

  enable_linting:
    type: bool
    help: "Whether to include linting in the CI workflow."
    default: true
```

### Field Reference Table

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `_metadata.name` | string | Required | Unique identifier for the module. Must be snake_case. | `example_module` |
| `_metadata.version` | string | Required | CalVer version string (see [CalVer section](#calver-versioning-convention)). | `"20240101.0"` |
| `_metadata.description` | string | Required | One-sentence human-readable description. | `"Adds standard CI."` |
| `questions` | mapping | Required | Input variables exposed to the consumer. | see below |
| `_exclude` | list | Optional | Glob patterns for files to exclude from rendering. | `["*.md"]` |
| `_tasks` | list | Optional | Shell commands to run after rendering (in target repo). | `["npm install"]` |
| `_jinja_extensions` | list | Optional | Jinja2 extensions to enable. | `["jinja2_time.TimeExtension"]` |
| `_subdirectory` | string | Optional | Subdirectory within the module to use as template root. | `"content"` |

Each entry under `questions` accepts:

| Sub-field | Type | Required | Description |
|---|---|---|---|
| `type` | string | Required | One of: `str`, `bool`, `int`, `float`, `yaml`, `json`. |
| `help` | string | Required | Prompt text shown to the user. |
| `default` | any | Optional | Default value used when no input is given. |
| `choices` | list | Optional | Restricts input to an enumerated set of values. |
| `validator` | string | Optional | Jinja2 expression that must evaluate to `true` for the value to be accepted. |
| `when` | string | Optional | Jinja2 expression; question is skipped when it evaluates to `false`. |
| `secret` | bool | Optional | Masks the value in prompts and logs. |

---

## Jinja2 Templating

Copier uses Jinja2 to render template files. Any file ending in `.jinja` is processed.

### Variable Substitution

Use `{{ variable_name }}` to insert a variable value:

```yaml
# content/.github/workflows/ci.yaml.jinja
name: "CI — {{ project_name }}"

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
```

### Control Flow

Use `{% %}` blocks for conditionals and loops:

```yaml
# content/.github/workflows/ci.yaml.jinja
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{% if enable_linting %}
      - name: Lint
        run: npm run lint
{% endif %}
{% for env in deploy_environments %}
  deploy-{{ env }}:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying to {{ env }}"
{% endfor %}
```

### Best Practices

- **StrictUndefined**: Copier enables `StrictUndefined` by default, causing rendering to fail immediately on any undefined variable reference. This catches typos early. Do not work around it by suppressing errors — fix the variable name.
- Keep logic in `copier.yaml` (`when`, `validator`) rather than embedding complex conditionals in templates. Templates should be readable.
- Prefer `{{ variable | default("fallback") }}` only for truly optional display values; required values should be declared as questions without defaults so Copier prompts the user.
- Use Jinja2 comments (`{# comment #}`) to explain non-obvious template logic. These are stripped from the rendered output.

---

## Variable Types and Validation

### Supported Types

| Type | Copier Keyword | Notes |
|---|---|---|
| Text string | `str` | Default type. Accepts any text. |
| Boolean | `bool` | Renders as `true`/`false` in YAML. |
| Integer | `int` | Validated as a whole number. |
| Float | `float` | Validated as a decimal number. |
| YAML structure | `yaml` | Parsed as YAML; use for lists and mappings. |
| JSON structure | `json` | Parsed as JSON. |

### Validation

Use the `validator` field to enforce constraints at input time. The value is a Jinja2 expression that must evaluate to `true`:

```yaml
questions:
  port:
    type: int
    help: "Port number for the service (1024–65535)."
    default: 8080
    validator: "{% if port >= 1024 and port <= 65535 %}true{% endif %}"

  module_name:
    type: str
    help: "Module identifier (lowercase letters, digits, and underscores only)."
    validator: "{% if module_name | regex_search('^[a-z][a-z0-9_]*$') %}true{% endif %}"
```

When validation fails, Copier re-prompts the user with the original help text.

### Conditional Questions

Use `when` to show a question only when relevant:

```yaml
questions:
  use_docker:
    type: bool
    help: "Does this service use Docker?"
    default: false

  docker_image:
    type: str
    help: "Base Docker image (e.g. node:20-alpine)."
    when: "{{ use_docker }}"
```

---

## Module Composition and Inheritance

### Composing Multiple Modules

GitWeave's strength is applying multiple modules to a single repository. Rather than monolithic templates, compose smaller focused modules:

- `modules/lang-node` — Node.js toolchain setup
- `modules/ci-basic` — Standard CI workflow
- `modules/dora-metrics` — DORA metric instrumentation

Composing modules is declared in the overlay config. Each managed repository has an entry in `config/repos/<repo-name>.yaml`:

```yaml
# config/repos/my-service.yaml
apiVersion: gitweave.io/v1
kind: ManagedRepo
metadata:
  name: my-service
spec:
  modules:
    - name: lang-node
      version: "20240601.0"
    - name: ci-basic
      version: "20240601.0"
    - name: dora-metrics
      version: "20240601.2"
```

The `gitweave-apply` workflow reads these specs and runs `copier update` for each module in sequence.

### Module Ordering

Modules are applied in the order listed under `spec.modules`. If two modules write to the same file, the last one wins. Design modules to own distinct file paths wherever possible.

### Inheritance via Subdirectories

Copier's `_subdirectory` field lets a parent module re-use a sub-tree:

```yaml
# modules/ci-extended/copier.yaml
_subdirectory: "content"

_inherit:
  - modules/ci-basic
```

Use this sparingly. Prefer composition over inheritance.

---

## Local Testing Workflow

Test your module locally before publishing.

### Prerequisites

```bash
pip install copier
```

### Step 1 — Apply the module to a temp directory

```bash
copier copy modules/<name> /tmp/test-output
```

Copier will prompt for each question defined in `copier.yaml`. Provide test values and inspect the output under `/tmp/test-output`.

For a non-interactive run (CI-friendly), supply answers on the command line:

```bash
copier copy modules/my_module /tmp/test-output \
  --data project_name=test-app \
  --data enable_linting=true \
  --defaults
```

### Step 2 — Inspect the output

```bash
ls -la /tmp/test-output
cat /tmp/test-output/.github/workflows/ci.yaml
```

Verify that variables were substituted correctly and that conditional blocks rendered as expected.

### Step 3 — Clean up between runs

Always remove the output directory before re-running to avoid stale state from a previous render:

```bash
rm -rf /tmp/test-output
```

Then re-run the `copier copy` command from Step 1.

### Step 4 — Simulate an update

Test that the module can be re-applied cleanly to an existing repo (the upgrade path):

```bash
# Initialize a fake consumer repo
git init /tmp/test-output
cd /tmp/test-output && git add . && git commit -m "init"

# Apply the module
copier copy ../modules/my_module /tmp/test-output --overwrite

# Simulate an update after bumping the module version
copier update --vcs-ref HEAD /tmp/test-output
```

---

## Your First Module

Follow these numbered steps to create and test a working module from scratch.

1. **Create the module directory.**

   ```bash
   mkdir -p modules/hello-world/content/.github/workflows
   ```

2. **Write `copier.yaml`.**

   ```yaml
   # modules/hello-world/copier.yaml
   _metadata:
     name: hello_world
     version: "20240101.0"
     description: "Adds a Hello World workflow to a repository."

   _subdirectory: "content"

   questions:
     project_name:
       type: str
       help: "The project name to display in the workflow."
       default: "my-project"
   ```

3. **Write a template file.**

   ```yaml
   # modules/hello-world/content/.github/workflows/hello.yaml.jinja
   name: "Hello World — {{ project_name }}"

   on:
     workflow_dispatch:

   jobs:
     greet:
       runs-on: ubuntu-latest
       steps:
         - name: Greet
           run: echo "Hello from {{ project_name }}!"
   ```

4. **Write a module README** (optional but recommended).

   ```markdown
   <!-- modules/hello-world/README.md -->
   # hello-world

   Adds a simple Hello World GitHub Actions workflow.

   ## Variables

   | Name | Type | Default | Description |
   |---|---|---|---|
   | `project_name` | str | `my-project` | Name displayed in the workflow. |
   ```

5. **Test the module locally.**

   ```bash
   rm -rf /tmp/test-output
   copier copy modules/hello-world /tmp/test-output --data project_name=acme-api --defaults
   cat /tmp/test-output/.github/workflows/hello.yaml
   ```

   You should see the rendered workflow with `acme-api` substituted in place of `{{ project_name }}`.

6. **Commit the module.**

   ```bash
   git add modules/hello-world/
   git commit -m "feat: add hello-world module"
   ```

7. **Publish (tag and push).** See the [Publishing](#publishing-a-module-update) section.

---

## CalVer Versioning Convention

GitWeave modules use **CalVer** with the format `YYYYMMDD.Patch`.

| Component | Format | Example |
|---|---|---|
| Date | Year, Month, Day concatenated | `20240601` |
| Patch | Integer starting at 0 | `0`, `1`, `2` |
| Combined | `YYYYMMDD.Patch` | `20240601.0` |

### Rules

- **New day, reset patch.** The first release on a new day is `YYYYMMDD.0`.
- **Same day, increment patch.** A second release on the same day becomes `YYYYMMDD.1`, then `YYYYMMDD.2`, and so on.
- The patch increment signals "multiple releases on the same day" to consumers without changing the date component.

### Examples

| Scenario | Version |
|---|---|
| First release on 1 Jan 2024 | `20240101.0` |
| Second release on 1 Jan 2024 | `20240101.1` |
| First release on 15 Jun 2025 | `20250615.0` |

### Where to Set the Version

Update `_metadata.version` in `copier.yaml` before tagging:

```yaml
_metadata:
  name: my_module
  version: "20250615.0"
```

---

## Publishing a Module Update

### Step-by-step

1. **Make your changes** to the module files and update `_metadata.version` in `copier.yaml`.

2. **Test locally** (see [Local Testing Workflow](#local-testing-workflow)).

3. **Commit your changes.**

   ```bash
   git add modules/my_module/
   git commit -m "feat(my_module): describe the change"
   ```

4. **Create a CalVer git tag.**

   Tag format: `v<module-name>/<YYYYMMDD.Patch>`

   ```bash
   git tag v20250615.0
   git push origin v20250615.0
   ```

   Or for a module-scoped tag:

   ```bash
   git tag modules/my_module/v20250615.0
   git push origin modules/my_module/v20250615.0
   ```

5. **Push to main.**

   ```bash
   git push origin main
   ```

6. **Propagation to consumers.** Pushing the tag triggers the `gitweave-apply` workflow, which opens pull requests in all consumer repositories that declare this module in their `config/repos/<repo>.yaml` overlay. Reviewers in each consumer repository then approve and merge their update PR.

---

## Conflict Resolution Runbook

When Copier re-applies a module to a repository that has local modifications, it performs a **3-way merge**: the previous template output, the new template output, and the consumer's local changes. Conflicts arise when the same region of a file was modified both by the module update and by a local change.

### Triggers

- Running `copier update` to upgrade a module in a consumer repository.
- A consumer repository has diverged from the last applied template version.

### What a Conflict Looks Like

```
<<<<<<< OLD (last applied template)
name: "CI — old-project"
=======
name: "CI — new-project"
>>>>>>> NEW (current template render)
```

Lines between `<<<<<<<` and `=======` are the HEAD (your local version). Lines between `=======` and `>>>>>>>` are the incoming template changes.

### Resolution Steps

1. **Run `copier update`** in the consumer repository. If there are no conflicts, it completes automatically. If conflicts exist, Copier reports them and exits non-zero.

   ```bash
   copier update
   ```

2. **Identify conflicted files** using `git status`. Conflicted files are marked `UU`.

   ```bash
   git status
   git diff
   ```

3. **Open each conflicted file** and resolve the conflict markers manually. Decide whether to keep the consumer's local change, accept the template update, or blend both.

4. **Verify `.copier-answers.yml`.** This file in the root of the consumer repository tracks which version of each module was last applied. After a successful update, Copier updates this file automatically. If it has conflict markers, resolve them by keeping the new version values.

   ```bash
   cat .copier-answers.yml
   ```

5. **Stage the resolved files.**

   ```bash
   git add <resolved-file>
   git add .copier-answers.yml
   ```

6. **Commit the resolution.**

   ```bash
   git commit -m "chore: resolve copier update conflicts for my_module v20250615.0"
   ```

7. **Verify the rendered output** by inspecting the key files affected by the module update and confirming they behave as expected.

### Prevention

- Keep local modifications to module-managed files minimal. If a file is owned by a module, customise it via module variables rather than direct edits.
- Add module-managed files to a comment in the repo README so contributors know which files not to modify by hand.
- Review `copier update` output regularly (e.g., in scheduled CI) to catch drift early.
