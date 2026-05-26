"""Notifier sub-agent — drafts and dispatches a notification in the
recipient's language after a verifier has approved the match.

Owns the `dispatch_notification` tool. Refuses without a valid decision_id —
both at the prompt level (system rule #5) and at the tool level (the tool
revalidates against Firestore).
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from agent.config import GEMINI_MODEL
from agent.prompts import NOTIFIER_PROMPT
from agent.tools.notify import dispatch_notification


def build_notifier_agent() -> LlmAgent:
    return LlmAgent(
        name="disasterlens_notifier",
        model=GEMINI_MODEL,
        description="Drafts and dispatches a notification in the recipient's "
                    "language. Refuses without a verifier decision_id.",
        instruction=NOTIFIER_PROMPT,
        tools=[dispatch_notification],
    )
