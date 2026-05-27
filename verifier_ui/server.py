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

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore
from pydantic import BaseModel

from agent.config import GCP_PROJECT_ID
from agent.tools.verifier import PENDING_COLLECTION
from data.personas import SHELTERS

VERIFIER_ID = "ui_verifier"
DIST_DIR = Path(__file__).resolve().parent / "dist"
# The seeker UI's built assets, when present, are served at /seeker/. In dev
# the Vite server runs on :5174 directly; in production both UIs ride one
# Cloud Run service to keep the cold-start budget low and the URL count down.
SEEKER_DIST_DIR = Path(__file__).resolve().parents[1] / "seeker_ui" / "dist"
# Seeker-uploaded photos. /tmp is ephemeral on Cloud Run — fine for hackathon
# scope (photos are short-lived; the verifier resolves the case within minutes
# and the photo's job is done). Production would put these in GCS with a
# signed URL TTL of, say, 24 hours.
PHOTO_DIR = Path("/tmp/disasterlens-photos")
PHOTO_DIR.mkdir(parents=True, exist_ok=True)
# Reasonable upload cap — DiceBear avatars are ~3 KB, real photos ~1-3 MB.
MAX_PHOTO_BYTES = 8 * 1024 * 1024
_ALLOWED_PHOTO_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


app = FastAPI(title="DisasterLens Verifier API")

# Permissive CORS for local dev (Vite at :5173 → API at :8787). Seeker UI
# also runs at :5174 during dev — added below.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
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
    # Set only when the verifier has confirmed a guardian relationship for an
    # under-18 candidate (school record, photo ID, cross-roster confirmation,
    # etc.). The endpoint enforces this: a minor cannot be approved without
    # `guardian_verified == True`. dispatch_notification re-checks server-side.
    guardian_verified: bool | None = None


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
    # Policy gate: a minor can only be APPROVED when guardian_verified is true.
    # Rejecting/asking-for-more-info on a minor does not require the flag.
    if (data.get("is_minor")
            and req.decision == "approved"
            and req.guardian_verified is not True):
        raise HTTPException(
            422,
            "candidate is_minor=true — guardian_verified must be true to approve",
        )
    update: dict = {
        "decision": req.decision,
        "verifier_id": VERIFIER_ID,
        "verifier_note": req.verifier_note,
        "decided_at": datetime.now(timezone.utc),
        "status": "decided",
    }
    if req.guardian_verified is not None:
        update["guardian_verified"] = req.guardian_verified
    doc_ref.update(update)
    return {"ok": True, "decision_id": decision_id, "decision": req.decision}


@app.get("/api/shelters")
def list_shelters() -> list[dict]:
    return SHELTERS


@app.get("/healthz")
def healthz() -> dict:
    """Cheap health probe — no Firestore / Elastic dependency. Used by the
    deploy script to measure cold-start latency without skewing it with
    upstream-handshake time."""
    return {"ok": True, "service": "verifier-ui"}


# ── Seeker photo upload ─────────────────────────────────────────────────
# The seeker UI posts a photo of the missing person here. We persist to /tmp
# under a random id, return a self-hosted URL the agent can hand into
# `photo_match` and `await_verifier`. No EXIF stripping yet — the demo data
# is synthetic, but production would strip GPS metadata before persisting.

@app.post("/api/seeker-photos")
async def upload_seeker_photo(request: Request, file: UploadFile = File(...)) -> dict:
    if file.content_type not in _ALLOWED_PHOTO_MIME:
        raise HTTPException(415, f"unsupported content-type {file.content_type!r}; "
                                  f"expected one of {sorted(_ALLOWED_PHOTO_MIME)}")
    body = await file.read()
    if len(body) > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"photo too large: {len(body)} bytes > {MAX_PHOTO_BYTES}")
    if len(body) == 0:
        raise HTTPException(400, "empty upload")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
           "image/heic": "heic", "image/heif": "heif"}[file.content_type]
    photo_id = f"sp_{secrets.token_urlsafe(10)}.{ext}"
    (PHOTO_DIR / photo_id).write_bytes(body)
    # Return an ABSOLUTE URL so the agent (which runs in a different process,
    # possibly a different host) can fetch it from `photo_match` without
    # having to be configured with the server's base URL.
    absolute = f"{request.url.scheme}://{request.url.netloc}/api/seeker-photos/{photo_id}"
    return {
        "photo_id": photo_id,
        "photo_url": absolute,
        "bytes": len(body),
        "content_type": file.content_type,
    }


@app.get("/api/seeker-photos/{photo_id}")
def get_seeker_photo(photo_id: str) -> FileResponse:
    # Reject path traversal; allowed alphabet is token_urlsafe + extension.
    if "/" in photo_id or ".." in photo_id:
        raise HTTPException(400, "invalid photo_id")
    path = PHOTO_DIR / photo_id
    if not path.exists():
        raise HTTPException(404, "photo not found (may have expired)")
    return FileResponse(path)


# ── Seeker chat endpoint ────────────────────────────────────────────────
# Drives the agent from the seeker-side React UI. One HTTP call per seeker
# turn; the call BLOCKS until the agent's run completes (including the
# verifier gate — the verifier UI must approve / reject in parallel for the
# call to return). The frontend renders a "agent is searching..." state and
# tolerates 60–120s response latency.

class SeekerChatRequest(BaseModel):
    message: str
    seeker_photo_url: str = ""
    session_id: str | None = None


@app.post("/api/seeker-chat")
async def seeker_chat(req: SeekerChatRequest) -> dict:
    if not req.message.strip():
        raise HTTPException(400, "empty message")
    # Lazy import — keeps the FastAPI module light when chat isn't in use.
    from agent.main import run_query_collect
    try:
        result = await run_query_collect(
            req.message,
            seeker_photo_url=req.seeker_photo_url,
            user_id="seeker_ui",
            session_id=req.session_id,
            emit_to_stdout=False,
        )
    except Exception as e:
        raise HTTPException(500, f"agent run failed: {type(e).__name__}: {e}")
    return result


# Serve the built UIs (after `npm run build` in each). Skipped when the
# dist/ directories don't exist, so dev (Vite at :5173 / :5174) still works.
# Mount the seeker UI FIRST — StaticFiles routing is registered-order
# dependent and the verifier mount at "/" otherwise shadows /seeker/*.
if SEEKER_DIST_DIR.exists():
    app.mount("/seeker", StaticFiles(directory=SEEKER_DIST_DIR, html=True), name="seeker-ui")
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="verifier-ui")
