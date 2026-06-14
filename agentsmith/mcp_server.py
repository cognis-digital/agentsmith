"""AGENTSMITH MCP server -- exposes run_crew() as an MCP tool."""
from __future__ import annotations

from agentsmith.core import CrewError, load_config, run_crew, to_json


def serve() -> int:
    """Start an MCP stdio server. Requires the optional mcp extra:
        pip install "cognis-agentsmith[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install cognis-agentsmith[mcp]")
        return 1
    app = FastMCP("agentsmith")

    @app.tool()
    def agentsmith_run(config: str) -> str:
        """Run a crew from a config file path. Returns JSON result report."""
        try:
            crew = load_config(config)
            return to_json(run_crew(crew))
        except CrewError as exc:
            return to_json({"ok": False, "error": str(exc)})

    app.run()
    return 0
