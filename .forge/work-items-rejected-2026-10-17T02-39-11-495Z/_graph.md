# Work-item dependency graph — INIT-2026-10-17-i4-modules-overlays

```mermaid
graph TD
    WI-1["WI-1: Ground hygiene (egg-info + rulesets 403)"]
    WI-2["WI-2: Copier modules (python_service + terraform_module)"]
    WI-3["WI-3: gw module render CLI"]
    WI-4["WI-4: Recording transport + no-PR invariant"]
    WI-5["WI-5: Overlay schema + policy schema"]
    WI-6["WI-6: Overlay apply engine (Git Trees API)"]
    WI-7["WI-7: gw overlay status"]
    WI-8["WI-8: gw plan overlay-aware + retire apply-overlays.py"]
    WI-9["WI-9: gw overlay request + policy"]
    WI-10["WI-10: I3b residuals #1-6"]
    WI-11["WI-11: Live acceptance tests"]
    WI-12["WI-12: Integration"]

    WI-2 --> WI-3
    WI-2 --> WI-6
    WI-3 --> WI-6
    WI-4 --> WI-6
    WI-5 --> WI-6
    WI-5 --> WI-9
    WI-6 --> WI-7
    WI-6 --> WI-8
    WI-7 --> WI-9
    WI-7 --> WI-11
    WI-8 --> WI-11
    WI-9 --> WI-10
    WI-9 --> WI-11
    WI-1 --> WI-12
    WI-10 --> WI-12
    WI-11 --> WI-12
```

## Layer summary

| Layer | WIs | Parallelisable |
|-------|-----|---------------|
| 0 | WI-1, WI-2, WI-4, WI-5 | 4 parallel |
| 1 | WI-3 | after WI-2 |
| 2 | WI-6 | after WI-2, WI-3, WI-4, WI-5 |
| 3 | WI-7, WI-8 | 2 parallel after WI-6 |
| 4 | WI-9 | after WI-7, WI-5 |
| 5 | WI-10, WI-11 | 2 parallel after WI-9 (WI-11 also after WI-8) |
| 6 | WI-12 | after WI-1, WI-10, WI-11 |

## cli.py edit chain

WI-3 adds `module` group → WI-6 adds `overlay` group → WI-7 adds `overlay status` → WI-9 adds `overlay request` → WI-10 updates `list-exceptions --team` optional

Each step depends_on the previous, serialising all cli.py edits. ✓

## overlays.py edit chain

WI-6 creates `gitweave/managers/overlays.py` → WI-7 extends it (WI-7 depends_on WI-6). ✓
