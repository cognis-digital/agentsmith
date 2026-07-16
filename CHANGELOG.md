# Changelog

## Unreleased

### Added
- `stats` subcommand and `describe_crew()` — structural metrics: wave count,
  max parallelism, roots/leaves, per-agent load, and the critical path.
- `critical_path()` — longest dependency chain through the workflow DAG.
- `graph` subcommand with `to_dot()` (Graphviz DOT) and `to_mermaid()` exporters.
- `scan()` / `to_json()` in `core` — the MCP `scan` tool now has a real
  implementation that returns a validation + plan report and never raises on
  bad input.
- `mcp` subcommand to launch the MCP stdio server.
- New test module `tests/test_features.py` (24 tests) covering the analysis and
  export features, edge cases, and the new CLI subcommands.
- CI matrix (Linux/macOS/Windows × Python 3.10–3.12) plus a ruff lint job.
- Docs: accurate README, `docs/USAGE.md`, refreshed `docs/ARCHITECTURE.md`, and
  an expanded `ROADMAP.md`.

### Changed
- `agentsmith/core.py` now declares `__all__` for a clean public API surface.

_All changes are additive; existing commands and public functions are unchanged._

## 0.1.x

- Add detection rule `AGE-100`.
