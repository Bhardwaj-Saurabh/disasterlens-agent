"""Coordinator — root LlmAgent.

Composition (per design.md §4):
    Coordinator (root)
    ├── sub_agents: Intake, Notifier
    └── tools:
        ├── elastic_mcp        (Elastic Agent Builder MCP, ~21 platform tools)
        ├── name_variants      (deterministic ICU+phonetic+nickname expansion)
        └── await_verifier     (LONG-RUNNING — HITL gate via Firestore)

The Coordinator owns the reasoning loop and the visible MCP calls. Intake and
Notifier are kept as sub-agents because they tell a clearer multi-agent story
in the demo trace, not because they're load-bearing on their own.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from agent.config import GEMINI_MODEL
from agent.intake import build_intake_agent
from agent.notifier import build_notifier_agent
from agent.prompts import COORDINATOR_PROMPT
from agent.tools.elastic import build_elastic_mcp_toolset
from agent.tools.name_variants import name_variants
from agent.tools.verifier import await_verifier


def build_coordinator_agent() -> LlmAgent:
    # Intake and Notifier are wrapped as AgentTools — callable, returns
    # control to the Coordinator with their output. The alternative
    # (sub_agents=[...]) does a one-way transfer and the Coordinator can't
    # resume, which breaks the multi-step reasoning loop.
    intake_tool = AgentTool(agent=build_intake_agent())
    notifier_tool = AgentTool(agent=build_notifier_agent())

    return LlmAgent(
        name="disasterlens_coordinator",
        model=GEMINI_MODEL,
        description="Root agent for DisasterLens — language-aware family "
                    "reunification across Elasticsearch shelter rosters, "
                    "missing-person reports, open cases, and social posts. "
                    "Verifier gate on every match.",
        instruction=COORDINATOR_PROMPT,
        tools=[
            intake_tool,
            notifier_tool,
            build_elastic_mcp_toolset(),
            name_variants,
            await_verifier,
        ],
    )
