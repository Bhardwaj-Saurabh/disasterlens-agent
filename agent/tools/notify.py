"""dispatch_notification — mocked SMS / Slack dispatcher.

Hackathon scope: no real telco integration. The dispatch creates a durable
record in Firestore (`dispatched_notifications/{decision_id}`) for the demo
trace AND prints a banner to stdout so the live demo shows the artifact.

Safety: refuses to dispatch without a valid `decision_id` that exists in
`pending_decisions/{decision_id}` AND has `decision == "approved"`. This is
the runtime backstop for system prompt rule #5 — the coordinator can't bypass
the gate even if the prompt is jailbroken.
"""
from __future__ import annotations

from datetime import datetime, timezone

from google.cloud import firestore

from agent.config import GCP_PROJECT_ID
from agent.tools.verifier import PENDING_COLLECTION

DISPATCHED_COLLECTION = "dispatched_notifications"


_firestore_client: firestore.Client | None = None


def _client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    return _firestore_client


def dispatch_notification(
    decision_id: str,
    recipient: str,
    language: str,
    body: str,
) -> dict:
    """Dispatch a (mocked) notification. REFUSES if the decision_id is missing,
    unknown, or not in `approved` status.

    Args:
        decision_id: From `await_verifier`. Validated against Firestore.
        recipient: Phone number / chat handle.
        language: ISO 639-1 of the body text.
        body: The notification text — already drafted in the recipient's language.

    Returns:
        On success: {"dispatched": true, "decision_id": ..., "preview": <first 80 chars>}.
        On refusal: {"dispatched": false, "error": "<reason>"}.
    """
    if not decision_id:
        return {"dispatched": False, "error": "missing decision_id — refused per safety rule #5"}

    pending_ref = _client().collection(PENDING_COLLECTION).document(decision_id)
    snap = pending_ref.get()
    if not snap.exists:
        return {"dispatched": False, "error": f"unknown decision_id={decision_id}"}
    data = snap.to_dict() or {}
    if data.get("decision") != "approved":
        return {"dispatched": False,
                "error": f"decision={data.get('decision')!r} — only 'approved' may dispatch"}

    record = {
        "decision_id": decision_id,
        "recipient": recipient,
        "language": language,
        "body": body,
        "dispatched_at": datetime.now(timezone.utc),
    }
    _client().collection(DISPATCHED_COLLECTION).document(decision_id).set(record)

    # Demo-visible banner — the agent's reply alone is too quiet for the video.
    print("┌─────────────────────────────────────────────────────────────────────────")
    print(f"│ 📨 DISPATCHED  decision={decision_id}  lang={language}  to={recipient}")
    print(f"│ {body}")
    print("└─────────────────────────────────────────────────────────────────────────")

    return {
        "dispatched": True,
        "decision_id": decision_id,
        "language": language,
        "recipient": recipient,
        "preview": body[:80] + ("…" if len(body) > 80 else ""),
    }
