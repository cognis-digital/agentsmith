# AGENTSMITH — Architecture

> Config-first scaffolding and orchestration for multi-agent workflows

A **crew** is a set of `Agent`s plus a DAG of `Task`s. The engine turns that
declarative config into a validated, deterministic execution plan.

```
crew.json ──▶ parse_config ──▶ validate_crew ──▶ plan_crew ──▶ run_crew ──▶ table · json
                  │                  │             (waves)         │
             dataclasses        structural                    render + execute
             (Agent/Task/         errors            ├──▶ describe_crew (stats + critical path)
              Crew)                                  └──▶ to_dot / to_mermaid (DAG export)
                                                                   │
                                                            MCP tool (agents)
```

## Data model (`agentsmith/core.py`)

- **`Agent`** — `id`, `role`, `goal`, `model`. Built via `Agent.from_dict`,
  which enforces a string id matching `^[A-Za-z0-9_.-]+$`.
- **`Task`** — `id`, `agent`, `prompt`, `depends_on`. Built via `Task.from_dict`,
  which enforces id shape and that `depends_on` is a list of strings.
- **`Crew`** — `name`, `agents`, `tasks`, with `agent_ids()` and `task_map()`
  helpers.

## Pipeline

1. **parse** — `parse_config(dict)` / `load_config(path)` build a `Crew`,
   raising `CrewError` on malformed shape (empty `agents`/`tasks`, bad types).
2. **validate** — `validate_crew(crew)` returns a list of human-readable errors:
   duplicate ids, unknown agent/task references, self-dependencies, dangling
   `{{placeholder}}` references (a prompt may only reference a declared
   dependency), and dependency cycles (DFS coloring, `_find_cycle`).
3. **plan** — `plan_crew(crew)` runs a Kahn topological sort and groups tasks
   into **parallel waves** (each wave = tasks with no remaining unmet deps).
   Ties are broken by id for determinism. Raises `CrewError` if invalid.
4. **run** — `run_crew(crew)` walks the waves in order. For each task it renders
   the prompt (`_render_prompt` substitutes `{{dep}}` with that dependency's
   output, so data flows through the DAG) and calls `_execute_task`, a
   deterministic SHA-256 digest of `(agent, role, model, rendered prompt)`. This
   is the single seam where you wire in a real model.

## Analysis & export

- **`describe_crew(crew)`** — summary metrics: agent/task/edge counts, wave
  count, `max_parallel`, roots, leaves, per-agent task load, and the
  **critical path**.
- **`critical_path(crew)`** — the longest dependency chain (memoized DFS,
  root→leaf order). Bounds the minimum sequential depth of the workflow.
- **`to_dot(crew)`** — Graphviz DOT rendering of the DAG (pure rendering; works
  even on a cyclic graph so you can *see* the cycle).
- **`to_mermaid(crew)`** — Mermaid `flowchart` rendering; task ids are mapped to
  stable synthetic node keys so ids containing `.`/`-` never break the parser.

## MCP surface (`agentsmith/mcp_server.py`)

`serve()` exposes `scan(target)` as an MCP tool: it loads a crew config and
returns a JSON report (`ok`, `errors`, and — when valid — the full
`describe_crew` summary). `scan` never raises for expected input problems; it
reports them in `errors` so an agent can react.

## Extending

Add a capability + a test + (optionally) a `demos/NN-*/SCENARIO.md`. Keep changes
additive and deterministic. See [CONTRIBUTING.md](../CONTRIBUTING.md).
