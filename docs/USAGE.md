# AGENTSMITH — Usage

Complete command reference and the crew-config schema. Every example below is
reproducible from a clone; nothing calls the network.

## Install

```bash
pip install -e .            # from a clone
# or
pipx install "git+https://github.com/cognis-digital/agentsmith.git"
```

Optional extras:

```bash
pip install -e ".[mcp]"      # MCP stdio server
pip install -e ".[connect]"  # cognis-connect emit bridge
pip install -e ".[dev]"      # pytest + ruff (for development)
```

## The crew config

A crew is a JSON object with a `name`, a non-empty `agents` list, and a
non-empty `tasks` list.

```json
{
  "name": "market-brief-crew",
  "agents": [
    {"id": "scout",  "role": "Research Analyst", "goal": "Collect sources", "model": "local"},
    {"id": "quant",  "role": "Market Analyst",   "goal": "Assess the setup", "model": "local"},
    {"id": "risk",   "role": "Risk Analyst",     "goal": "Surface downside", "model": "local"},
    {"id": "editor", "role": "Editor",           "goal": "Synthesize a brief", "model": "local"}
  ],
  "tasks": [
    {"id": "gather", "agent": "scout", "prompt": "Collect sources on critical-minerals equities"},
    {"id": "analyze_market", "agent": "quant", "prompt": "Score momentum from: {{gather}}", "depends_on": ["gather"]},
    {"id": "analyze_risk",   "agent": "risk",  "prompt": "List risks from: {{gather}}",     "depends_on": ["gather"]},
    {"id": "write_brief", "agent": "editor", "prompt": "Brief. Market: {{analyze_market}} Risk: {{analyze_risk}}", "depends_on": ["analyze_market", "analyze_risk"]}
  ]
}
```

### Field reference

| Field | Required | Default | Rules |
|---|---|---|---|
| `name` | no | `"crew"` | any string |
| `agents[].id` | **yes** | — | `^[A-Za-z0-9_.-]+$`, unique |
| `agents[].role` | no | `""` | free-form |
| `agents[].goal` | no | `""` | free-form |
| `agents[].model` | no | `"local"` | free-form label |
| `tasks[].id` | **yes** | — | `^[A-Za-z0-9_.-]+$`, unique |
| `tasks[].agent` | **yes** | — | must be a declared agent id |
| `tasks[].prompt` | no | `""` | may contain `{{dep_id}}` |
| `tasks[].depends_on` | no | `[]` | list of task ids |

**Placeholder rule:** every `{{x}}` in a prompt must appear in that task's
`depends_on`. At run time it is replaced with dependency `x`'s output.

## Commands

### `init [name]`

Print a runnable starter config to stdout (always JSON).

```bash
agentsmith init research-crew > crew.json
```

### `validate <config>`

Structural validation. Exit `0` when valid, `1` when invalid.

```console
$ agentsmith validate crew.json
crew: market-brief-crew
OK: 4 agents, 4 tasks
```

```console
$ agentsmith --format json validate broken.json
{
  "command": "validate",
  "ok": false,
  "crew": "broken",
  "errors": ["task 'x' references unknown agent 'ghost'"]
}
```

### `plan <config>`

Show the topological execution plan as parallel waves.

```console
$ agentsmith plan crew.json
plan for crew 'market-brief-crew' (3 wave(s)):
  wave 0: gather
  wave 1: analyze_market, analyze_risk
  wave 2: write_brief
```

### `stats <config>`

Structural metrics: waves, max parallelism, roots/leaves, per-agent load, and
the critical path (longest dependency chain).

```console
$ agentsmith stats crew.json
crew: market-brief-crew
agents: 4  tasks: 4  edges: 4
waves: 3  max parallel: 2
roots: gather
leaves: write_brief
critical path (3): gather -> analyze_market -> write_brief
tasks per agent:
  editor: 1
  quant: 1
  risk: 1
  scout: 1
```

`--format json` emits the full metrics object (including `critical_path` and
`critical_path_length`).

### `graph <config> [--syntax dot|mermaid]`

Export the task DAG for visualization. Default syntax is Graphviz DOT.

```console
$ agentsmith graph crew.json | dot -Tpng -o crew.png     # render with Graphviz
$ agentsmith graph crew.json --syntax mermaid            # paste into any Mermaid renderer
```

### `run <config>`

Validate, plan, and execute the workflow. Output is deterministic.

```console
$ agentsmith run crew.json
run crew 'market-brief-crew' (4 step(s)):
  [w0] gather -> [scout] gather::<digest>
  [w1] analyze_market -> [quant] analyze_market::<digest>
  [w1] analyze_risk -> [risk] analyze_risk::<digest>
  [w2] write_brief -> [editor] write_brief::<digest>
final: [editor] write_brief::<digest>
```

Machine-readable output:

```bash
agentsmith run crew.json --format json | jq '.steps[].task'
```

### `mcp`

Launch the MCP stdio server (requires the `[mcp]` extra). It exposes a
`scan(target)` tool that loads a crew config and returns its validation + plan
report as JSON.

```bash
pip install -e ".[mcp]"
agentsmith mcp
```

## Using the Python API

```python
from agentsmith import (
    parse_config, load_config, validate_crew, plan_crew, run_crew,
    describe_crew, critical_path, to_dot, to_mermaid, scan,
)

crew = load_config("crew.json")
assert validate_crew(crew) == []          # [] means valid
waves = plan_crew(crew)                    # [["gather"], ["analyze_market", "analyze_risk"], ...]
report = run_crew(crew)                    # {"steps": [...], "final": "...", ...}
print(critical_path(crew))                 # longest dependency chain
print(to_mermaid(crew))                    # Mermaid flowchart source
print(scan("crew.json")["ok"])             # MCP-facing report, never raises on bad input
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | success / valid |
| `1` | invalid config, planning error, missing file, or missing extra |
| `2` | no subcommand given (help is printed) |

## CI gating

```yaml
- name: Validate crew config
  run: |
    pip install -e .
    agentsmith validate crew.json   # exits 1 on a structurally invalid config
```
