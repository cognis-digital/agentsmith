"""AGENTSMITH MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from agentsmith.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-agentsmith[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-agentsmith[mcp]'")
        return 1
    app = FastMCP("agentsmith")

    @app.tool()
    def agentsmith_scan(target: str) -> str:
        """Config-first scaffolding and orchestration for multi-agent workflows. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
