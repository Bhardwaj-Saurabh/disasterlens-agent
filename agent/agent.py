"""Agent root export — discovery point for the ADK dev UI.

`adk dev --module agent.agent` looks for `root_agent` here.
`adk deploy` does too.
"""
from __future__ import annotations

from agent.coordinator import build_coordinator_agent

root_agent = build_coordinator_agent()
