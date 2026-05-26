"""Sprint 1 Day 1 hello-world.

Goal: prove the ADK ↔ Elastic Agent Builder MCP round-trip works end-to-end.

What this does:
  1. Connects ADK's MCPToolset to Elastic Agent Builder MCP over HTTP.
  2. Lists discovered MCP tools (proves auth + transport work).
  3. Asks Gemini, via an ADK agent, to call `core_index_explorer` and report
     the cluster's indices in plain language.

If this prints discovered tools AND a sentence from Gemini naming at least one
index, Day 1 is unblocked. Sprint 2 starts on Day 2.

If it fails, the failure mode tells us which unknown to investigate:
  • auth/transport error      → MCP endpoint URL or API-key scope is wrong
  • tool discovery empty      → Agent Builder MCP not enabled on this cluster
  • Gemini call fails         → Vertex IAM (roles/aiplatform.user) missing,
                                ADC not run, or model id not on Vertex
  • agent runs but no tools   → McpToolset wiring mismatch

Confirmed against Elastic Cloud Serverless 9.5 + google-adk 2.1.0:
  • MCP is served by Kibana (.kb. host), not Elasticsearch
  • Streamable HTTP transport, not SSE
  • google-genai must be routed via Vertex (GOOGLE_GENAI_USE_VERTEXAI=true);
    Gemini-API-only model ids like gemini-2.0-flash-exp will 404 on Vertex.
"""
import asyncio

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from google.genai import types

from agent.config import (
    ELASTIC_API_KEY,
    GEMINI_MODEL,
    KIBANA_ENDPOINT,
)

# Agent Builder MCP is served by Kibana (not Elasticsearch) at /api/agent_builder/mcp
# over Streamable HTTP. Confirmed against Elastic Cloud Serverless 9.5.
ELASTIC_MCP_URL = f"{KIBANA_ENDPOINT.rstrip('/')}/api/agent_builder/mcp"


def build_elastic_mcp_toolset() -> McpToolset:
    """Wire ADK's McpToolset to Elastic Agent Builder MCP over Streamable HTTP."""
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=ELASTIC_MCP_URL,
            headers={"Authorization": f"ApiKey {ELASTIC_API_KEY}"},
        )
    )


def build_agent() -> LlmAgent:
    return LlmAgent(
        name="disasterlens_helloworld",
        model=GEMINI_MODEL,
        instruction=(
            "You are a Sprint 1 Day 1 connectivity test for DisasterLens. "
            "Call the `core_index_explorer` tool (or equivalent index-listing tool) "
            "on the connected Elastic cluster and report back, in one sentence, "
            "how many indices you found and the name of one of them. "
            "If no index-listing tool is available, name the tools you do see."
        ),
        tools=[build_elastic_mcp_toolset()],
    )


async def main() -> None:
    agent = build_agent()

    # Print discovered tools — this alone proves MCP auth + transport work.
    toolset: McpToolset = agent.tools[0]  # type: ignore[assignment]
    discovered = await toolset.get_tools()
    print(f"[hello-world] discovered {len(discovered)} MCP tools:")
    for tool in discovered:
        print(f"  • {tool.name}")
    if not discovered:
        print("[hello-world] no tools discovered — check MCP URL, API-key scope, "
              "and that Agent Builder is enabled on the cluster.")
        return

    # Now actually run the agent and prove Gemini can drive a tool call.
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="disasterlens_day1",
        agent=agent,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="disasterlens_day1", user_id="day1", session_id="s1"
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text="List the indices in the cluster.")],
    )

    print("\n[hello-world] running agent…")
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"[hello-world] agent: {part.text}")


if __name__ == "__main__":
    asyncio.run(main())
