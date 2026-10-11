# Rejected work-item set

This set failed the project-manager phase's own validation and was moved here so that
nothing downstream could claim it. It is kept, not deleted, because it is the evidence
for why the decomposition failed.

## Set errors

- REJECTED.md: unparseable — work item missing required field: work_item_id
- WI-3: creates lists 7 path(s), exceeding the D-18 sizing bound of 5 — split into smaller work items
- acceptance criteria not exercised by any work item's quality_gate_cmd: AC5 (uncarried: `python3 -m pytest tests/`; when: it is read and `python3 -m pytest tests/` runs). Add or edit a work item whose gate runs each named command as written.
