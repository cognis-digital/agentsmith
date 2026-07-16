# AGENTSMITH — Roadmap

Direction for `agentsmith`, the config-first multi-agent workflow orchestrator.
Priorities are shaped in the open — open an issue or PR to weigh in.

## Now (v0.1.x — shipped / in progress)

- Config-first engine: `parse` → `validate` → `plan` (parallel waves) → `run`
  (deterministic, offline execution with real data-flow between tasks).
- CLI: `init`, `validate`, `plan`, `run`, plus `stats` (metrics + critical path)
  and `graph` (Graphviz DOT / Mermaid export).
- MCP server (`agentsmith mcp`) exposing a `scan(target)` report tool.
- `table` / `json` output, CI-friendly exit codes.
- CI matrix (Linux/macOS/Windows × Python 3.10–3.12) with lint + tests.
- Reference ports in JavaScript, Go, and Rust (`ports/`).

## Next (v0.2)

- **Config formats** — accept YAML in addition to JSON for authoring ergonomics.
- **Model seam** — a documented, pluggable executor interface so a real model
  (local or hosted) can be dropped into `run` without touching the planner.
- **Retries & timeouts** — per-task execution policy (attempts, backoff, deadline)
  surfaced in the report.
- **Richer stats** — per-wave timing estimates and fan-in/fan-out hotspots.
- **Export targets** — JSON-graph and SVG (via Graphviz) output from `graph`.
- **Schema** — publish a JSON Schema for crew configs and validate against it.

## Later (v1.0)

- **Plugin API** — third-party executors, validators, and exporters via entry
  points.
- **Sub-crews** — compose crews as reusable, nestable units.
- **Live run streaming** — incremental step events for long-running workflows.
- **PyPI release** and versioned, documented stability guarantees.
- **Commercial tier + support** for production deployments (licensing@cognis.digital).

## Non-goals

- Becoming a heavyweight, opinionated agent runtime. `agentsmith` stays a small,
  deterministic *orchestration substrate* you wire your own models and tools into.

Open an issue or PR to shape priorities — see [CONTRIBUTING.md](CONTRIBUTING.md).
