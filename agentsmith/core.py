"""Core engine for AGENTSMITH.

A Crew is a set of Agents plus a DAG of Tasks. The engine validates the config
(unknown agent refs, unknown deps, duplicate ids, cycles), computes a topological
execution plan grouped into parallel 'waves', and runs the plan deterministically.

Execution is a real, pure-Python simulation: each task renders its prompt template
with outputs from its dependencies (so data actually flows through the DAG), and
produces a deterministic output digest. No network, no LLM calls required -- this
is the orchestration substrate you wire a real model into.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


__all__ = [
    "Agent",
    "Task",
    "Crew",
    "CrewError",
    "parse_config",
    "load_config",
    "validate_crew",
    "plan_crew",
    "run_crew",
    "scaffold_config",
    "critical_path",
    "describe_crew",
    "to_dot",
    "to_mermaid",
    "to_json",
    "scan",
]


class CrewError(Exception):
    """Raised on invalid config or unsatisfiable workflow."""


_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}")


@dataclass
class Agent:
    id: str
    role: str = ""
    goal: str = ""
    model: str = "local"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Agent":
        if not isinstance(d, dict):
            raise CrewError("agent entry must be an object")
        aid = d.get("id")
        if not aid or not isinstance(aid, str):
            raise CrewError("agent missing string 'id'")
        if not _ID_RE.match(aid):
            raise CrewError(f"agent id '{aid}' has illegal characters")
        return cls(
            id=aid,
            role=str(d.get("role", "")),
            goal=str(d.get("goal", "")),
            model=str(d.get("model", "local")),
        )


@dataclass
class Task:
    id: str
    agent: str
    prompt: str = ""
    depends_on: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        if not isinstance(d, dict):
            raise CrewError("task entry must be an object")
        tid = d.get("id")
        if not tid or not isinstance(tid, str):
            raise CrewError("task missing string 'id'")
        if not _ID_RE.match(tid):
            raise CrewError(f"task id '{tid}' has illegal characters")
        agent = d.get("agent")
        if not agent or not isinstance(agent, str):
            raise CrewError(f"task '{tid}' missing string 'agent'")
        deps = d.get("depends_on", []) or []
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
            raise CrewError(f"task '{tid}' depends_on must be a list of strings")
        return cls(id=tid, agent=agent, prompt=str(d.get("prompt", "")), depends_on=list(deps))


@dataclass
class Crew:
    name: str
    agents: List[Agent]
    tasks: List[Task]

    def agent_ids(self) -> set:
        return {a.id for a in self.agents}

    def task_map(self) -> Dict[str, Task]:
        return {t.id: t for t in self.tasks}


def parse_config(data: Dict[str, Any]) -> Crew:
    """Build a Crew from a parsed config dict (raises CrewError on bad shape)."""
    if not isinstance(data, dict):
        raise CrewError("config root must be a JSON object")
    name = str(data.get("name", "crew"))
    raw_agents = data.get("agents")
    raw_tasks = data.get("tasks")
    if not isinstance(raw_agents, list) or not raw_agents:
        raise CrewError("config needs a non-empty 'agents' list")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise CrewError("config needs a non-empty 'tasks' list")
    agents = [Agent.from_dict(a) for a in raw_agents]
    tasks = [Task.from_dict(t) for t in raw_tasks]
    return Crew(name=name, agents=agents, tasks=tasks)


def load_config(path: str) -> Crew:
    """Load and parse a crew config JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise CrewError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CrewError(f"invalid JSON in {path}: {exc}") from exc
    return parse_config(data)


def validate_crew(crew: Crew) -> List[str]:
    """Return a list of human-readable error strings. Empty == valid."""
    errors: List[str] = []

    # Duplicate agent ids
    seen_a: set = set()
    for a in crew.agents:
        if a.id in seen_a:
            errors.append(f"duplicate agent id: {a.id}")
        seen_a.add(a.id)

    # Duplicate task ids
    seen_t: set = set()
    for t in crew.tasks:
        if t.id in seen_t:
            errors.append(f"duplicate task id: {t.id}")
        seen_t.add(t.id)

    agent_ids = crew.agent_ids()
    task_ids = {t.id for t in crew.tasks}

    for t in crew.tasks:
        if t.agent not in agent_ids:
            errors.append(f"task '{t.id}' references unknown agent '{t.agent}'")
        for dep in t.depends_on:
            if dep == t.id:
                errors.append(f"task '{t.id}' depends on itself")
            elif dep not in task_ids:
                errors.append(f"task '{t.id}' depends on unknown task '{dep}'")
        # Unresolvable prompt placeholders must reference a declared dependency
        for ref in _PLACEHOLDER_RE.findall(t.prompt):
            if ref not in t.depends_on:
                errors.append(
                    f"task '{t.id}' prompt uses {{{{{ref}}}}} but does not depend on '{ref}'"
                )

    # Cycle detection (only if structural refs are otherwise sane)
    if not errors:
        cyc = _find_cycle(crew)
        if cyc:
            errors.append("dependency cycle: " + " -> ".join(cyc))
    return errors


def _find_cycle(crew: Crew) -> Optional[List[str]]:
    tmap = crew.task_map()
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tmap}
    stack: List[str] = []

    def dfs(node: str) -> Optional[List[str]]:
        color[node] = GRAY
        stack.append(node)
        for dep in tmap[node].depends_on:
            if dep not in color:
                continue
            if color[dep] == GRAY:
                idx = stack.index(dep)
                return stack[idx:] + [dep]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for tid in sorted(tmap):
        if color[tid] == WHITE:
            found = dfs(tid)
            if found:
                return found
    return None


def plan_crew(crew: Crew) -> List[List[str]]:
    """Kahn topological sort grouped into parallel waves.

    Each inner list is a set of task ids with no remaining unmet deps -- they
    can run concurrently. Ties broken by id for determinism.
    """
    errors = validate_crew(crew)
    if errors:
        raise CrewError("; ".join(errors))
    tmap = crew.task_map()
    indeg = {tid: 0 for tid in tmap}
    dependents: Dict[str, List[str]] = {tid: [] for tid in tmap}
    for t in crew.tasks:
        for dep in t.depends_on:
            indeg[t.id] += 1
            dependents[dep].append(t.id)

    ready = sorted([tid for tid, d in indeg.items() if d == 0])
    waves: List[List[str]] = []
    done = 0
    while ready:
        waves.append(list(ready))
        nxt: List[str] = []
        for tid in ready:
            done += 1
            for child in dependents[tid]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    nxt.append(child)
        ready = sorted(nxt)
    if done != len(tmap):
        raise CrewError("dependency cycle detected during planning")
    return waves


def _render_prompt(prompt: str, dep_outputs: Dict[str, str]) -> str:
    def sub(m: "re.Match") -> str:
        return dep_outputs.get(m.group(1), m.group(0))

    return _PLACEHOLDER_RE.sub(sub, prompt)


def _execute_task(task: Task, agent: Agent, rendered: str) -> str:
    """Deterministic stand-in for an agent step.

    Produces a stable digest of (agent, role, rendered prompt) so the same
    config always yields the same workflow result -- wire a real model in here.
    """
    payload = f"{agent.id}|{agent.role}|{agent.model}|{rendered}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"[{agent.id}] {task.id}::{digest}"


def run_crew(crew: Crew) -> Dict[str, Any]:
    """Validate, plan, and execute the crew. Returns a result report."""
    waves = plan_crew(crew)
    amap = {a.id: a for a in crew.agents}
    tmap = crew.task_map()
    outputs: Dict[str, str] = {}
    steps: List[Dict[str, Any]] = []
    for wave_idx, wave in enumerate(waves):
        for tid in wave:
            task = tmap[tid]
            agent = amap[task.agent]
            dep_outputs = {d: outputs[d] for d in task.depends_on}
            rendered = _render_prompt(task.prompt, dep_outputs)
            out = _execute_task(task, agent, rendered)
            outputs[tid] = out
            steps.append(
                {
                    "wave": wave_idx,
                    "task": tid,
                    "agent": agent.id,
                    "prompt": rendered,
                    "output": out,
                }
            )
    return {
        "crew": crew.name,
        "agents": len(crew.agents),
        "tasks": len(crew.tasks),
        "waves": waves,
        "max_parallel": max((len(w) for w in waves), default=0),
        "steps": steps,
        "final": steps[-1]["output"] if steps else None,
    }


def critical_path(crew: Crew) -> List[str]:
    """Return the longest dependency chain (by task count) through the DAG.

    The returned list is ordered root -> leaf and represents the sequence of
    tasks that bounds the minimum number of sequential steps the workflow needs,
    regardless of how much parallelism is available. Raises ``CrewError`` if the
    crew is structurally invalid or cyclic.
    """
    errors = validate_crew(crew)
    if errors:
        raise CrewError("; ".join(errors))
    tmap = crew.task_map()
    memo: Dict[str, List[str]] = {}

    def longest(tid: str) -> List[str]:
        if tid in memo:
            return memo[tid]
        best: List[str] = []
        for dep in tmap[tid].depends_on:
            cand = longest(dep)
            if len(cand) > len(best):
                best = cand
        memo[tid] = best + [tid]
        return memo[tid]

    overall: List[str] = []
    for tid in sorted(tmap):
        candidate = longest(tid)
        if len(candidate) > len(overall):
            overall = candidate
    return overall


def describe_crew(crew: Crew) -> Dict[str, Any]:
    """Return a structural summary of a crew (counts, waves, roots/leaves, etc.).

    Raises ``CrewError`` if the crew is invalid (it computes the execution plan,
    which requires a sound DAG).
    """
    waves = plan_crew(crew)
    tmap = crew.task_map()
    dependents: Dict[str, List[str]] = {tid: [] for tid in tmap}
    for t in crew.tasks:
        for dep in t.depends_on:
            dependents[dep].append(t.id)
    roots = sorted(t.id for t in crew.tasks if not t.depends_on)
    leaves = sorted(tid for tid, ds in dependents.items() if not ds)
    per_agent: Dict[str, int] = {}
    for t in crew.tasks:
        per_agent[t.agent] = per_agent.get(t.agent, 0) + 1
    cpath = critical_path(crew)
    return {
        "crew": crew.name,
        "agents": len(crew.agents),
        "tasks": len(crew.tasks),
        "edges": sum(len(t.depends_on) for t in crew.tasks),
        "waves": len(waves),
        "max_parallel": max((len(w) for w in waves), default=0),
        "roots": roots,
        "leaves": leaves,
        "tasks_per_agent": dict(sorted(per_agent.items())),
        "critical_path": cpath,
        "critical_path_length": len(cpath),
    }


def to_dot(crew: Crew) -> str:
    """Render the task DAG as a Graphviz DOT graph (no validation required)."""
    safe_name = crew.name.replace("\\", "\\\\").replace('"', '\\"')
    lines: List[str] = [
        f'digraph "{safe_name}" {{',
        "  rankdir=LR;",
        "  node [shape=box, style=rounded];",
    ]
    for t in crew.tasks:
        label = f"{t.id}\\n({t.agent})"
        lines.append(f'  "{t.id}" [label="{label}"];')
    for t in crew.tasks:
        for dep in t.depends_on:
            lines.append(f'  "{dep}" -> "{t.id}";')
    lines.append("}")
    return "\n".join(lines)


def to_mermaid(crew: Crew) -> str:
    """Render the task DAG as a Mermaid ``flowchart`` (no validation required).

    Task ids are mapped to stable synthetic node keys (``n0``, ``n1``, ...) so
    that ids containing ``.`` or ``-`` never confuse Mermaid's parser, while the
    human-readable id is preserved in each node label.
    """
    key = {t.id: f"n{i}" for i, t in enumerate(crew.tasks)}
    lines: List[str] = ["flowchart LR"]
    for t in crew.tasks:
        lines.append(f'    {key[t.id]}["{t.id}<br/>({t.agent})"]')
    for t in crew.tasks:
        for dep in t.depends_on:
            if dep in key:
                lines.append(f"    {key[dep]} --> {key[t.id]}")
    return "\n".join(lines)


def to_json(obj: Any) -> str:
    """Serialize any JSON-able report object to a stable, indented string."""
    return json.dumps(obj, indent=2, sort_keys=False)


def scan(target: str) -> Dict[str, Any]:
    """Load a crew config from ``target`` and return a structural report.

    This powers the MCP tool: it never raises for expected input problems --
    a missing file or an invalid config is reported in the ``errors`` field so
    an agent can read the result and react. On a valid config it embeds the full
    :func:`describe_crew` summary.
    """
    try:
        crew = load_config(target)
    except CrewError as exc:
        return {"ok": False, "target": target, "errors": [str(exc)]}
    errors = validate_crew(crew)
    report: Dict[str, Any] = {"crew": crew.name, "ok": not errors, "errors": errors}
    if not errors:
        report.update(describe_crew(crew))
    return report


def scaffold_config(name: str = "research-crew") -> Dict[str, Any]:
    """Emit a runnable starter crew config (the config-first scaffold)."""
    return {
        "name": name,
        "agents": [
            {"id": "researcher", "role": "Research Analyst", "goal": "Gather facts", "model": "local"},
            {"id": "writer", "role": "Editor", "goal": "Write a brief", "model": "local"},
        ],
        "tasks": [
            {"id": "gather", "agent": "researcher", "prompt": "Collect sources on the topic"},
            {
                "id": "draft",
                "agent": "writer",
                "prompt": "Write a brief using: {{gather}}",
                "depends_on": ["gather"],
            },
        ],
    }
