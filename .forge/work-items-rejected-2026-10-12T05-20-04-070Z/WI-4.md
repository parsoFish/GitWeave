---
work_item_id: WI-4
initiative_id: INIT-2026-10-11-i3b-self-service
status: pending
depends_on:
  - WI-1
  - WI-2
acceptance_criteria:
  - given: "team policy allows 'content-update' and setting is in team's allowed_content_settings"
    when: "self_serve_update_content(team, repo_name, setting, value, gh_org, policy, caller_login) is called"
    then: "applies the setting via the appropriate GitHub API call on the repo object and returns success"
  - given: "setting type 'branch_protection' with a rule dict"
    when: "update_content is called"
    then: "calls repo.get_branch(branch).edit_protection with the provided parameters"
  - given: "setting type 'topics'"
    when: "update_content is called"
    then: "calls repo.replace_topics with the provided list"
  - given: "setting type not in team's allowed_content_settings in policy"
    when: "update_content is called"
    then: "raises PolicyDenied naming the setting and the rule"
  - given: "team not in policy"
    when: "update_content is called"
    then: "raises PolicyDenied naming the team"
files_in_scope:
  - gitweave/self_serve/update_content.py
  - tests/test_self_serve_update_content.py
creates:
  - gitweave/self_serve/update_content.py
  - tests/test_self_serve_update_content.py
estimated_iterations: 3
quality_gate_cmd:
  - pytest
  - "-q"
  - "tests/test_self_serve_update_content.py::TestUpdateContent::test_policy_violation_exits_nonzero"
  - "-p"
  - "no:cacheprovider"
domain: "self-serve"
---

# WI-4: gw self-serve update-content

Target: `gitweave/self_serve/update_content.py` — apply repo settings a team admin may self-serve. Module instances are explicitly excluded (I4 scope).

## Supported setting types

- `branch_protection` — `repo.get_branch(branch).edit_protection(**kwargs)`
- `repo_variables` — `repo.create_variable(name, value)` / `repo.update_variable`
- `environments` — `repo.create_environment(env_name)`
- `topics` — `repo.replace_topics(topics_list)`
- `description` — `repo.edit(description=value)`

## Function contract

```python
def self_serve_update_content(
    team: str,
    repo_name: str,
    setting: str,     # one of the supported types above
    value,            # type-appropriate value
    gh_org,
    policy: dict,
    caller_login: str,
) -> dict:
    """Apply *setting*=*value* to *repo_name*.

    Raises PolicyDenied if team lacks permission for this setting type.
    Returns {"applied": True}.
    Never opens a PR on the control repository.
    """
```

## Tests (unit — mock gh_org and repo)

`test_policy_violation_exits_nonzero` — collection fails until file is created.

## Brain themes consulted

- `brain/projects/gitweave/profile.md`
- `brain/cycles/themes/spec-driven-work-items.md`
- `brain/cycles/themes/quality-gate-cmd-must-assert-new-work.md`
