"""DisasterLens agent configuration.

Load-bearing constants — safety thresholds, model id, confidence floor for HITL.
See docs/design.md §7 (Safety Configuration) for the three-layer rationale.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from google.genai import types as genai_types

load_dotenv(".env.local")

# ── GCP / Vertex ─────────────────────────────────────────────────────────
GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# ── Elastic ──────────────────────────────────────────────────────────────
ELASTIC_ENDPOINT = os.environ["ELASTIC_ENDPOINT"]
ELASTIC_API_KEY = os.environ["ELASTIC_API_KEY"]
# Agent Builder MCP is on Kibana, not Elasticsearch. Derive .kb. from .es. if unset.
# (See memory:project-elastic-mcp-endpoint.)
KIBANA_ENDPOINT = os.environ.get(
    "KIBANA_ENDPOINT",
    ELASTIC_ENDPOINT.replace(".es.", ".kb."),
)
ELASTIC_MCP_URL = f"{KIBANA_ENDPOINT.rstrip('/')}/api/agent_builder/mcp"

# Index names — keep aligned with data/mappings/
INDEX_SHELTER_ROSTERS = "shelter_rosters"
INDEX_MISSING_PERSON_REPORTS = "missing_person_reports"
INDEX_REUNIFICATION_CASES = "reunification_cases"
INDEX_SOCIAL_REPORTS = "social_reports"

# Inference endpoint id for client-side embedding (data/embed.py and runtime kNN queries).
INFERENCE_ID = "disasterlens_e5"

# ── Thresholds (HITL + scoring) ──────────────────────────────────────────
# Coordinator system prompt rule #6: if best-candidate confidence < this, the
# agent must ask the seeker for one distinguishing detail before invoking
# await_verifier. Tuning lever for precision/recall trade-off.
LOW_CONFIDENCE_FLOOR = 0.75

# await_verifier polling: how long to wait for a verifier decision before
# timing out the agent run.
VERIFIER_TIMEOUT_SECONDS = 30 * 60  # 30 minutes
VERIFIER_POLL_INTERVAL_SECONDS = 1.0

# ── Safety (Gemini) ──────────────────────────────────────────────────────
# Load-bearing in a missing-persons domain (design.md §7). Lower thresholds
# than defaults — we'd rather block a marginal output than risk a hallucinated
# "we found your grandson at Shelter X."
SAFETY_SETTINGS: list[genai_types.SafetySetting] = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]
