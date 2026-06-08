# Demo 01 - Basic research crew

A realistic config-first multi-agent workflow: a **researcher**, two parallel
**analysts**, and a **writer** that synthesizes their findings into a brief.

The DAG forces ordering and surfaces parallelism:

```
gather ---> analyze_market  --\
        \-> analyze_risk    ---> write_brief
```

- `gather` runs first (no deps).
- `analyze_market` and `analyze_risk` both depend only on `gather`, so they
  form a single parallel **wave**.
- `write_brief` depends on both analyses and uses `{{analyze_market}}` and
  `{{analyze_risk}}` placeholders, so their outputs actually flow into its prompt.

## Run it

```bash
# validate the config structure (unknown refs, cycles, dangling placeholders)
python -m agentsmith validate demos/01-basic/crew.json

# see the topological plan grouped into parallel waves
python -m agentsmith --format json plan demos/01-basic/crew.json

# execute the workflow (deterministic, no network)
python -m agentsmith run demos/01-basic/crew.json

# scaffold a fresh starter config
python -m agentsmith init my-crew > crew.json
```

Expected plan: `wave 0: gather`, `wave 1: analyze_market, analyze_risk`,
`wave 2: write_brief`.
