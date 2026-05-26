"""Intake sub-agent — multilingual structured-case extraction.

Takes the seeker's free-text request (any language) and returns a JSON case
record. No tools — pure LLM extraction with a strict output contract.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agent.config import GEMINI_MODEL
from agent.prompts import INTAKE_PROMPT


def build_intake_agent() -> LlmAgent:
    return LlmAgent(
        name="disasterlens_intake",
        model=GEMINI_MODEL,
        description="Extracts a structured case record (subject details, "
                    "seeker language, distinguishing features) from the "
                    "seeker's free-text request in any language.",
        instruction=INTAKE_PROMPT,
    )
