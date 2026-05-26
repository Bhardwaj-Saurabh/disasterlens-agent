"""Elastic Agent Builder MCP toolset factory.

Connects to the Kibana-hosted Agent Builder MCP server over Streamable HTTP
(see memory:project-elastic-mcp-endpoint for the .es./.kb. gotcha that took
out Sprint 1 Day 1). Discovers ~21 platform tools at runtime, of which the
agent prompts steer toward `platform_core_search` and `platform_core_execute_esql`.
"""
from __future__ import annotations

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from agent.config import ELASTIC_API_KEY, ELASTIC_MCP_URL


def build_elastic_mcp_toolset() -> McpToolset:
    """ADK MCPToolset wired to Elastic Agent Builder MCP via Streamable HTTP."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=ELASTIC_MCP_URL,
            headers={"Authorization": f"ApiKey {ELASTIC_API_KEY}"},
        )
    )
