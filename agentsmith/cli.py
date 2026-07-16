"""Command-line interface for AGENTSMITH.

Subcommands:
  validate <config>   Check a crew config for structural errors.
  plan <config>       Show the topological execution plan (parallel waves).
  run <config>        Validate, plan, and execute the workflow.
  init [name]         Print a runnable starter crew config.
  stats <config>      Print structural metrics (waves, critical path, fan-in/out).
  graph <config>      Export the task DAG as Graphviz DOT or Mermaid.
  mcp                 Launch the MCP stdio server (requires the [mcp] extra).

Global: --version, --format {table,json}
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import TOOL_NAME, TOOL_VERSION
from .core import (
    CrewError,
    describe_crew,
    load_config,
    plan_crew,
    run_crew,
    scaffold_config,
    to_dot,
    to_mermaid,
    validate_crew,
)


def _emit(obj, fmt: str, lines: Optional[List[str]] = None) -> None:
    if fmt == "json":
        print(json.dumps(obj, indent=2))
    else:
        for ln in (lines or []):
            print(ln)


def _cmd_validate(args) -> int:
    crew = load_config(args.config)
    errors = validate_crew(crew)
    ok = not errors
    obj = {"command": "validate", "ok": ok, "crew": crew.name, "errors": errors}
    lines = [f"crew: {crew.name}"]
    if ok:
        lines.append(f"OK: {len(crew.agents)} agents, {len(crew.tasks)} tasks")
    else:
        lines.append(f"INVALID ({len(errors)} error(s)):")
        lines.extend(f"  - {e}" for e in errors)
    _emit(obj, args.format, lines)
    return 0 if ok else 1


def _cmd_plan(args) -> int:
    crew = load_config(args.config)
    waves = plan_crew(crew)
    obj = {
        "command": "plan",
        "crew": crew.name,
        "waves": waves,
        "max_parallel": max((len(w) for w in waves), default=0),
    }
    lines = [f"plan for crew '{crew.name}' ({len(waves)} wave(s)):"]
    for i, w in enumerate(waves):
        lines.append(f"  wave {i}: {', '.join(w)}")
    _emit(obj, args.format, lines)
    return 0


def _cmd_run(args) -> int:
    crew = load_config(args.config)
    report = run_crew(crew)
    report["command"] = "run"
    lines = [f"run crew '{report['crew']}' ({len(report['steps'])} step(s)):"]
    for s in report["steps"]:
        lines.append(f"  [w{s['wave']}] {s['task']} -> {s['output']}")
    lines.append(f"final: {report['final']}")
    _emit(report, args.format, lines)
    return 0


def _cmd_init(args) -> int:
    cfg = scaffold_config(args.name)
    # init always emits JSON config (it's a config-first tool); table shows summary
    if args.format == "table":
        print(f"# starter crew '{cfg['name']}' -- save as crew.json")
    print(json.dumps(cfg, indent=2))
    return 0


def _cmd_stats(args) -> int:
    crew = load_config(args.config)
    info = describe_crew(crew)
    obj = dict(info)
    obj["command"] = "stats"
    lines = [
        f"crew: {info['crew']}",
        f"agents: {info['agents']}  tasks: {info['tasks']}  edges: {info['edges']}",
        f"waves: {info['waves']}  max parallel: {info['max_parallel']}",
        f"roots: {', '.join(info['roots']) or '(none)'}",
        f"leaves: {', '.join(info['leaves']) or '(none)'}",
        f"critical path ({info['critical_path_length']}): "
        + (" -> ".join(info["critical_path"]) or "(none)"),
        "tasks per agent:",
    ]
    for agent_id, count in info["tasks_per_agent"].items():
        lines.append(f"  {agent_id}: {count}")
    _emit(obj, args.format, lines)
    return 0


def _cmd_graph(args) -> int:
    crew = load_config(args.config)
    if args.syntax == "mermaid":
        print(to_mermaid(crew))
    else:
        print(to_dot(crew))
    return 0


def _cmd_mcp(args) -> int:
    from .mcp_server import serve

    return serve()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=TOOL_NAME, description="Config-first multi-agent workflow orchestration.")
    p.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    p.add_argument("--format", choices=["table", "json"], default="table", help="output format")
    sub = p.add_subparsers(dest="command")

    pv = sub.add_parser("validate", help="validate a crew config")
    pv.add_argument("config")
    pv.set_defaults(func=_cmd_validate)

    pp = sub.add_parser("plan", help="show execution plan (parallel waves)")
    pp.add_argument("config")
    pp.set_defaults(func=_cmd_plan)

    pr = sub.add_parser("run", help="validate, plan and execute the workflow")
    pr.add_argument("config")
    pr.set_defaults(func=_cmd_run)

    pi = sub.add_parser("init", help="print a runnable starter crew config")
    pi.add_argument("name", nargs="?", default="research-crew")
    pi.set_defaults(func=_cmd_init)

    ps = sub.add_parser("stats", help="print structural metrics for a crew config")
    ps.add_argument("config")
    ps.set_defaults(func=_cmd_stats)

    pg = sub.add_parser("graph", help="export the task DAG (Graphviz DOT or Mermaid)")
    pg.add_argument("config")
    pg.add_argument(
        "--syntax",
        choices=["dot", "mermaid"],
        default="dot",
        help="graph output syntax (default: dot)",
    )
    pg.set_defaults(func=_cmd_graph)

    pm = sub.add_parser("mcp", help="launch the MCP stdio server (needs the [mcp] extra)")
    pm.set_defaults(func=_cmd_mcp)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except CrewError as exc:
        if getattr(args, "format", "table") == "json":
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
