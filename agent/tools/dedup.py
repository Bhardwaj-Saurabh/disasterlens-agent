"""check_existing_case — seeker-side deduplication.

When María opens a case for Carlos, then her daughter opens another, then
Carlos's school opens a third, the Coordinator should recognise the overlap
and attach the new seekers to the *one* case rather than spawning parallel
investigations that race each other to the verifier queue.

Mechanism:
  • search reunification_cases for any open case (status != "verified",
    != "closed_false_match") whose `subject_name_variants_explored` keyword
    field intersects ANY surface form produced by `data.variants.expand(name)`
    plus the original.
  • return the first hit (oldest open case wins — that seeker has been waiting
    longest), or `{found: false}` if nothing overlaps.
  • the Coordinator follows up with `attach_seeker(case_id, seeker_*)` to
    register the new seeker as an additional contact and stop the run.

The actual ES search is delegated to the existing Elastic MCP `platform_core_search`
tool the agent already has — this module is a thin Python helper that builds the
query body. It also writes the `additional_seekers` field on the matched case
when the agent calls `attach_seeker`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from elasticsearch import Elasticsearch

from agent.config import (
    ELASTIC_API_KEY,
    ELASTIC_ENDPOINT,
    INDEX_REUNIFICATION_CASES,
)
from data.variants import expand

# Statuses that should NOT match — these cases are already resolved and a new
# seeker for the same subject is opening a genuinely new investigation.
_TERMINAL_STATUSES = ("verified", "closed_false_match", "closed_no_match")

_es_client: Elasticsearch | None = None


def _client() -> Elasticsearch:
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch(
            hosts=[ELASTIC_ENDPOINT],
            api_key=ELASTIC_API_KEY,
            request_timeout=15,
        )
    return _es_client


def _surface_forms(subject_name: str) -> list[str]:
    forms = [subject_name] + [v.surface_form for v in expand(subject_name)]
    # de-dup case-insensitively while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for f in forms:
        k = f.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


def check_existing_case(subject_name: str, subject_age: int | None = None) -> dict:
    """Look for an open reunification case whose subject overlaps `subject_name`.

    Call this BEFORE `await_verifier`. If `found` is True, do NOT proceed to
    open a new candidate match — instead call `attach_seeker(case_id, ...)` and
    tell the seeker another family member is already searching.

    Args:
        subject_name: The subject the new seeker is asking about, preserving
            script and diacritics. We expand variants internally.
        subject_age: Optional. When supplied, filters out cases whose
            `subject_age_estimate` differs by more than 5 years — prevents
            false dedup between two people who happen to share a common name.

    Returns:
        On match:
          {
            "found": true,
            "case_id": "rc_0007",
            "subject_name_as_given": "Carlos Martínez",
            "subject_age_estimate": 15,
            "status": "pending_verifier",
            "created_at": "...",
            "matched_variant": "Carlos Martinez",
            "additional_seeker_count": 2
          }
        On miss:
          {"found": false, "searched_variants": ["Carlos Martínez", "Carlos Martinez", ...]}
    """
    forms = _surface_forms(subject_name)

    must_not = [{"terms": {"status": list(_TERMINAL_STATUSES)}}]
    should = [
        {"term": {"subject_name_variants_explored": form}}
        for form in forms
    ]
    query: dict = {
        "size": 5,
        "sort": [{"created_at": "asc"}],
        "query": {
            "bool": {
                "must_not": must_not,
                "should": should,
                "minimum_should_match": 1,
            }
        },
    }
    if subject_age is not None:
        # The age field is optional on the index; use a range filter that
        # tolerates ±5 years. Cases with no age estimate still match (the
        # filter is wrapped in a `should` so the absence doesn't exclude).
        query["query"]["bool"].setdefault("filter", []).append({
            "bool": {
                "should": [
                    {"range": {"subject_age_estimate": {
                        "gte": subject_age - 5, "lte": subject_age + 5
                    }}},
                    {"bool": {"must_not": {"exists": {"field": "subject_age_estimate"}}}},
                ]
            }
        })

    resp = _client().search(index=INDEX_REUNIFICATION_CASES, body=query)
    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        return {"found": False, "searched_variants": forms}

    top = hits[0]
    src = top["_source"]
    # Best-effort surface-form match — which of our variants is in the hit's
    # variants_explored list? Useful for the Coordinator to explain "another
    # seeker asked about <X>" to the new seeker.
    hit_variants = set(src.get("subject_name_variants_explored") or [])
    matched_variant = next((f for f in forms if f in hit_variants), forms[0])

    return {
        "found": True,
        "case_id": src.get("case_id"),
        "subject_name_as_given": src.get("subject_name_as_given"),
        "subject_age_estimate": src.get("subject_age_estimate"),
        "status": src.get("status"),
        "created_at": src.get("created_at"),
        "matched_variant": matched_variant,
        "additional_seeker_count": len(src.get("additional_seekers") or []),
    }


def attach_seeker(
    case_id: str,
    seeker_name: str,
    seeker_language: str,
    seeker_contact: str,
    relationship: str = "",
) -> dict:
    """Attach a new seeker to an existing case as an additional contact.

    Use this when `check_existing_case` returned `found: true`. The agent
    should then stop the run (no new `await_verifier`) and inform the seeker
    that another family member is already searching.

    Args:
        case_id: The `case_id` returned by `check_existing_case`.
        seeker_name: Name of the new seeker (as they gave it).
        seeker_language: ISO 639-1 of the new seeker's language.
        seeker_contact: Phone / chat handle to reach them on.
        relationship: Optional self-described relationship to the subject
            ("grandmother", "neighbour", etc.).

    Returns:
        {"ok": true, "case_id": ..., "additional_seeker_count": <new count>}
        on success, or {"ok": false, "error": ...} if the case doesn't exist
        or is in a terminal status.
    """
    es = _client()
    try:
        snap = es.get(index=INDEX_REUNIFICATION_CASES, id=case_id)
    except Exception as e:  # NotFoundError or transport error
        return {"ok": False, "error": f"case {case_id} not found: {e}"}

    src = snap.get("_source") or {}
    if src.get("status") in _TERMINAL_STATUSES:
        return {"ok": False,
                "error": f"case {case_id} is in terminal status {src.get('status')!r} — "
                         "open a new case instead"}

    additional = list(src.get("additional_seekers") or [])
    additional.append({
        "seeker_name": seeker_name,
        "seeker_language": seeker_language,
        "seeker_contact": seeker_contact,
        "relationship": relationship,
        "attached_at": datetime.now(timezone.utc).isoformat(),
    })
    es.update(
        index=INDEX_REUNIFICATION_CASES,
        id=case_id,
        body={"doc": {"additional_seekers": additional}},
    )
    return {
        "ok": True,
        "case_id": case_id,
        "additional_seeker_count": len(additional),
    }
