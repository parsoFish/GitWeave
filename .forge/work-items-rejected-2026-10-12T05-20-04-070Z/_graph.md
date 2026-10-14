# Work-item dependency graph — INIT-2026-10-11-i3b-self-service

```mermaid
graph TD
    WI-1["WI-1: Policy engine + self_serve package scaffold"]
    WI-2["WI-2: Two-identity auth (caller token)"]
    WI-3["WI-3: gw self-serve new-repo"]
    WI-4["WI-4: gw self-serve update-content"]
    WI-5["WI-5: gw self-serve add-member / remove-member"]
    WI-6["WI-6: Policy exception recording"]
    WI-7["WI-7: CLI wiring (gw self-serve subcommands)"]
    WI-8["WI-8: Plan engine three-state branches"]
    WI-9["WI-9: Live acceptance tests"]

    WI-1 --> WI-3
    WI-1 --> WI-4
    WI-1 --> WI-5
    WI-1 --> WI-6
    WI-2 --> WI-3
    WI-2 --> WI-4
    WI-2 --> WI-5
    WI-2 --> WI-6
    WI-3 --> WI-7
    WI-4 --> WI-7
    WI-5 --> WI-7
    WI-6 --> WI-7
    WI-3 --> WI-8
    WI-5 --> WI-8
    WI-6 --> WI-8
    WI-7 --> WI-9
    WI-8 --> WI-9
```

## Parallelism

- **Layer 0** (parallel): WI-1, WI-2
- **Layer 1** (parallel after layer 0): WI-3, WI-4, WI-5, WI-6
- **Layer 2** (parallel after WI-3/4/5/6): WI-7, WI-8
- **Layer 3**: WI-9
