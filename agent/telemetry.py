"""Per-process cost telemetry — tracks token usage + tool calls + ES queries
so the README's cost-per-case claim is grounded in real numbers, not a guess.

Lightweight: no exporter, no OpenTelemetry. We accumulate counts in a
process-local dict, expose them via `/api/cost-stats` on the verifier UI
server, and reset on demand. Production would forward to Cloud Monitoring;
the hackathon scope is "show a credible number on the demo's eval slide."

Cost model — VERTEX AI pricing as of the cutoff date (2026-01); update
[PRICING_URL] if the rates change:
    gemini-2.5-flash input:        $0.075 per 1M tokens
    gemini-2.5-flash output:       $0.30  per 1M tokens
    text-embedding (E5 via Elastic): bundled in Elastic Cloud Serverless;
        we count requests but the marginal $ is ~$0.

Elastic queries: counted but not priced — Serverless billing is by VCU,
not by per-query, and the rate for hackathon-scale traffic is well below
$0.001 per reunification case.

The numbers we report are MARGINAL — the per-additional-case cost given
the infrastructure is already running, not the all-in TCO. The README and
demo should say so.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

PRICING_URL = "https://cloud.google.com/vertex-ai/generative-ai/pricing"

# USD per 1M tokens — updated 2026-01 from Vertex AI pricing page.
_GEMINI_PRICES_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "gemini-2.5-flash":     {"input": 0.075,  "output": 0.30},
    "gemini-2.5-flash-8b":  {"input": 0.0375, "output": 0.15},
    "gemini-2.5-pro":       {"input": 1.25,   "output": 5.00},
    # Fallback — assume flash rates for unknown models so we never crash a
    # demo on a price-table miss.
    "_default":             {"input": 0.075,  "output": 0.30},
}


class CostTracker:
    """Thread-safe accumulator. One singleton per process (the agent has only
    one process per Cloud Run instance)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started_at = datetime.now(timezone.utc)
            self._llm_calls: list[dict] = []
            self._tool_calls: dict[str, int] = defaultdict(int)
            self._es_queries: int = 0
            self._photo_match_calls: int = 0
            self._cases_run: int = 0

    def record_llm_call(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "",
    ) -> None:
        prices = _GEMINI_PRICES_PER_M_TOKENS.get(model) or _GEMINI_PRICES_PER_M_TOKENS["_default"]
        cost_usd = (
            (input_tokens / 1_000_000) * prices["input"]
            + (output_tokens / 1_000_000) * prices["output"]
        )
        with self._lock:
            self._llm_calls.append({
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": round(cost_usd, 6),
                "purpose": purpose,
                "at": datetime.now(timezone.utc).isoformat(),
            })

    def record_tool_call(self, name: str) -> None:
        with self._lock:
            self._tool_calls[name] += 1

    def record_es_query(self) -> None:
        with self._lock:
            self._es_queries += 1

    def record_photo_match(self) -> None:
        with self._lock:
            self._photo_match_calls += 1

    def record_case_run(self) -> None:
        """Call once per end-to-end reunification run. Lets /api/cost-stats
        compute a meaningful per-case average."""
        with self._lock:
            self._cases_run += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total_input = sum(c["input_tokens"] for c in self._llm_calls)
            total_output = sum(c["output_tokens"] for c in self._llm_calls)
            total_cost = sum(c["cost_usd"] for c in self._llm_calls)
            n_llm_calls = len(self._llm_calls)
            n_cases = max(self._cases_run, 1)
            by_purpose: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
            for c in self._llm_calls:
                p = c["purpose"] or "unspecified"
                by_purpose[p]["calls"] += 1
                by_purpose[p]["cost_usd"] += c["cost_usd"]
            return {
                "started_at": self._started_at.isoformat(),
                "n_cases_run": self._cases_run,
                "n_llm_calls": n_llm_calls,
                "n_tool_calls_total": sum(self._tool_calls.values()),
                "tool_call_counts": dict(self._tool_calls),
                "n_es_queries": self._es_queries,
                "n_photo_match_calls": self._photo_match_calls,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_cost_usd": round(total_cost, 4),
                "marginal_cost_per_case_usd": round(total_cost / n_cases, 4),
                "by_purpose": {p: {"calls": d["calls"],
                                    "cost_usd": round(d["cost_usd"], 4)}
                               for p, d in by_purpose.items()},
                "pricing_source": PRICING_URL,
                "pricing_table_used": _GEMINI_PRICES_PER_M_TOKENS,
            }


# Process-singleton. Imported by the FastAPI server and the agent's tools
# / Notifier wrappers. Reset on demand via /api/cost-stats/reset.
tracker = CostTracker()
