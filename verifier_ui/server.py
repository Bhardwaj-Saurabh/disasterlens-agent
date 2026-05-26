"""FastAPI proxy for the verifier UI.

Exposes the Firestore `pending_decisions` collection as a small REST API the
React app polls. Also serves the built static UI from `verifier_ui/dist/` so
the whole thing is one process in production.

Why not Firebase Web SDK + onSnapshot? Real-time onSnapshot would be slick but
requires the user to provision a Firebase Web App in the Firebase Console
(apiKey, authDomain, ...). Polling at 1s gives the same demo UX with zero
additional user setup — server reuses the same ADC the agent uses.

Endpoints:
  GET  /api/pending                — list pending_decisions where decision is null
  GET  /api/decisions/{id}         — fetch one decision
  POST /api/decisions/{id}/decide  — write decision + verifier_id + verifier_note
  GET  /api/shelters               — return the 10 Houston shelters for map pins
  GET  /                           — static UI (when built)

Run:
    uv run uvicorn verifier_ui.server:app --reload --port 8787
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore
from pydantic import BaseModel

from agent.config import GCP_PROJECT_ID
from agent.tools.verifier import PENDING_COLLECTION
from data.personas import SHELTERS

VERIFIER_ID = "ui_verifier"
DIST_DIR = Path(__file__).resolve().parent / "dist"


app = FastAPI(title="DisasterLens Verifier API")

# Permissive CORS for local dev (Vite at :5173 → API at :8787)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_firestore_client: firestore.Client | None = None


def _client() -> firestore.Client:
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT_ID)
    return _firestore_client


def _serialise(snap: firestore.DocumentSnapshot) -> dict:
    """Firestore → JSON-safe dict (datetimes become ISO strings)."""
    data = snap.to_dict() or {}
    for k, v in list(data.items()):
        if hasattr(v, "isoformat"):  # datetime
            data[k] = v.isoformat()
    data["_id"] = snap.id
    return data


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "request_more_info"]
    verifier_note: str = ""


@app.get("/api/pending")
def list_pending() -> list[dict]:
    """All decisions awaiting human input, oldest first."""
    snaps = _client().collection(PENDING_COLLECTION).where(
        filter=firestore.FieldFilter("decision", "==", None)
    ).stream()
    docs = [_serialise(s) for s in snaps]
    docs.sort(key=lambda d: d.get("created_at", ""))
    return docs


@app.get("/api/decisions/{decision_id}")
def get_decision(decision_id: str) -> dict:
    snap = _client().collection(PENDING_COLLECTION).document(decision_id).get()
    if not snap.exists:
        raise HTTPException(404, f"decision {decision_id} not found")
    return _serialise(snap)


@app.post("/api/decisions/{decision_id}/decide")
def decide(decision_id: str, req: DecisionRequest) -> dict:
    doc_ref = _client().collection(PENDING_COLLECTION).document(decision_id)
    snap = doc_ref.get()
    if not snap.exists:
        raise HTTPException(404, f"decision {decision_id} not found")
    data = snap.to_dict() or {}
    if data.get("decision") is not None:
        raise HTTPException(409, f"decision {decision_id} already decided as "
                                  f"{data.get('decision')!r}")
    doc_ref.update({
        "decision": req.decision,
        "verifier_id": VERIFIER_ID,
        "verifier_note": req.verifier_note,
        "decided_at": datetime.now(timezone.utc),
        "status": "decided",
    })
    return {"ok": True, "decision_id": decision_id, "decision": req.decision}


@app.get("/api/shelters")
def list_shelters() -> list[dict]:
    return SHELTERS


# Serve the built UI (after `npm run build`). Skipped if dist/ doesn't exist
# so dev (Vite at :5173) still works.
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="ui")
