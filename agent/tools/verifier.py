"""await_verifier long-running tool — the HITL gate.

Mechanism (per design.md §6):
  1. Tool writes a `pending_decisions/{decision_id}` doc to Firestore.
  2. Verifier UI (React + Firestore real-time listener) shows the pending doc.
  3. Verifier approves/rejects → UI writes the `decision` field on the same doc.
  4. This tool polls the doc every {VERIFIER_POLL_INTERVAL_SECONDS}s until
     `decision` appears, then returns it. The agent run resumes.

For Sprint 2 backend-only, the React UI is replaced by agent/verifier_cli.py
which writes the same `decision` field. The agent code stays unchanged when
the UI lands.

Polling rationale: simpler than snapshot listeners + asyncio.Future glue, and
the 1s latency is invisible in a 3-min demo. Switch to onSnapshot only if a
load test surfaces a need.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

from google.cloud import firestore

from agent.config import (
    GCP_PROJECT_ID,
    VERIFIER_POLL_INTERVAL_SECONDS,
    VERIFIER_TIMEOUT_SECONDS,
)

PENDING_COLLECTION = "pending_decisions"


_firestore_client: firestore.Client | None = None


def _client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    return _firestore_client


async def await_verifier(
    candidate_name: str,
    candidate_shelter: str,
    candidate_person_id: str,
    confidence: float,
    evidence: str,
    seeker_query: str,
    seeker_language: str,
    disclosure_consent: bool,
    is_minor: bool,
    candidate_age: int | None = None,
    seeker_location_text: str = "",
    seeker_lat: float | None = None,
    seeker_lon: float | None = None,
    candidate_photo_url: str = "",
    seeker_photo_url: str = "",
    photo_match_summary: str = "",
) -> dict:
    """LONG-RUNNING. Write a pending decision to Firestore and poll for the
    verifier's response.

    This is the canonical HITL gate. Every match destined for an
    externally-visible action (dispatch_notification, case approval) must
    flow through here first.

    Args:
        candidate_name: The surface name as it appears in the matched index doc.
        candidate_shelter: Shelter id where the candidate was found.
        candidate_person_id: The ES `_id` of the matched doc (for traceability).
        confidence: Agent's combined confidence score in [0, 1].
        evidence: One-sentence justification ("name match via nickname, age
            match, school affiliation consistent").
        seeker_query: The seeker's original query text.
        seeker_language: ISO 639-1 code of the seeker's language.
        disclosure_consent: The candidate's `disclosure_consent` boolean from
            the roster record. The verifier UI surfaces this as a policy badge;
            `dispatch_notification` refuses to send when this is False.
        is_minor: True when `candidate_age < 18`. The verifier UI requires an
            explicit guardian-verification checkbox before approval is allowed,
            and `dispatch_notification` refuses to send unless that flag is set
            on the decision doc.
        candidate_age: Persisted for the verifier UI badge; informative only.
        seeker_location_text: Human-readable last-known location from Intake
            (e.g., "Memorial High School", "Sharpstown"). Persisted for the
            verifier UI's map pin.
        seeker_lat / seeker_lon: Result of `geocode_location(seeker_location_text)`.
            Pass both or neither. The UI uses these to place the seeker pin
            and animate the arc to the candidate's shelter.
        candidate_photo_url: The `intake_photo_url` from the candidate roster
            doc, when present. The verifier UI renders this on the candidate
            side of the comparison panel.
        seeker_photo_url: The photo the seeker uploaded for the subject, if
            any. Rendered next to the candidate's photo for the verifier.
        photo_match_summary: One-sentence rollup of the `photo_match` tool
            output ("Gemini Vision: same person likely, glasses + grey hair
            agree, age range plausible"). Used in the verifier UI as part of
            the evidence chain — gives the verifier the model's read without
            having to pull up Firestore.

    Returns:
        A dict with `decision_id`, `decision` ('approved' | 'rejected' |
        'request_more_info' | 'timeout'), `verifier_id`, `verifier_note`,
        `decided_at`, plus the gate fields `disclosure_consent`, `is_minor`,
        and `guardian_verified` so the Notifier can re-check them.
    """
    decision_id = f"dec_{uuid4().hex[:12]}"
    doc_ref = _client().collection(PENDING_COLLECTION).document(decision_id)

    seeker_location = None
    if seeker_lat is not None and seeker_lon is not None:
        seeker_location = {"lat": float(seeker_lat), "lon": float(seeker_lon)}

    doc_ref.set({
        "decision_id": decision_id,
        "status": "pending",
        "candidate_name": candidate_name,
        "candidate_shelter": candidate_shelter,
        "candidate_person_id": candidate_person_id,
        "candidate_age": candidate_age,
        "candidate_photo_url": candidate_photo_url or None,
        "seeker_photo_url": seeker_photo_url or None,
        "photo_match_summary": photo_match_summary or None,
        "confidence": confidence,
        "evidence": evidence,
        "seeker_query": seeker_query,
        "seeker_language": seeker_language,
        "seeker_location_text": seeker_location_text,
        "seeker_location": seeker_location,
        "disclosure_consent": bool(disclosure_consent),
        "is_minor": bool(is_minor),
        # Guardian verification: only meaningful when is_minor. Starts null;
        # the verifier UI flips this to True after the verifier confirms the
        # seeker's guardian relationship out-of-band (school record, photo ID,
        # cross-roster confirmation, etc.). dispatch_notification re-checks.
        "guardian_verified": None,
        "created_at": datetime.now(timezone.utc),
        "decision": None,
        "verifier_id": None,
        "verifier_note": None,
        "decided_at": None,
    })

    deadline = time.time() + VERIFIER_TIMEOUT_SECONDS
    while time.time() < deadline:
        snap = doc_ref.get()
        data = snap.to_dict() or {}
        if data.get("decision"):
            return {
                "decision_id": decision_id,
                "decision": data["decision"],
                "verifier_id": data.get("verifier_id"),
                "verifier_note": data.get("verifier_note"),
                "decided_at": data.get("decided_at").isoformat()
                              if data.get("decided_at") else None,
                "disclosure_consent": data.get("disclosure_consent"),
                "is_minor": data.get("is_minor"),
                "guardian_verified": data.get("guardian_verified"),
            }
        await asyncio.sleep(VERIFIER_POLL_INTERVAL_SECONDS)

    # Timed out — leave the doc as pending; the verifier can still act on it
    # later, but this agent run gives up.
    return {
        "decision_id": decision_id,
        "decision": "timeout",
        "verifier_id": None,
        "verifier_note": f"no decision received within {VERIFIER_TIMEOUT_SECONDS}s",
        "decided_at": None,
        "disclosure_consent": bool(disclosure_consent),
        "is_minor": bool(is_minor),
        "guardian_verified": None,
    }
