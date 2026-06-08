"""AGENTSMITH - config-first scaffolding & orchestration for multi-agent workflows.

Define a crew of agents and a task DAG in a single JSON config, then validate,
plan (topological order with parallel waves), and run it deterministically.
Standard library only, zero install.
"""
from .core import (
    Agent,
    Task,
    Crew,
    CrewError,
    load_config,
    parse_config,
    validate_crew,
    plan_crew,
    run_crew,
    scaffold_config,
)

TOOL_NAME = "agentsmith"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Agent",
    "Task",
    "Crew",
    "CrewError",
    "load_config",
    "parse_config",
    "validate_crew",
    "plan_crew",
    "run_crew",
    "scaffold_config",
    "TOOL_NAME",
    "TOOL_VERSION",
]
