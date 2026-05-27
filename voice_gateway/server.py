"""Twilio Voice + SMS gateway — the phone entry point.

A Houston-area Twilio number routes to this FastAPI app. The caller picks a
language via DTMF, describes the missing person in their own language, and
hears the agent's reply (and optionally receives an SMS). The agent is the
same Coordinator the chat UI uses — voice is just a new front door.

Twilio webhook flow:

   inbound call ── POST /voice/incoming
                    │
                    ▼
              Say (en/multilingual greeting)
              Gather DTMF 1–4 ── action=/voice/lang
                    │
                    ▼
   /voice/lang ── locks the locale on this call (CALL_LOCALE[sid] = "es")
                  Say (greeting in chosen language)
                  Gather speech in chosen language ── action=/voice/speech
                    │
                    ▼
   /voice/speech ── kicks off background asyncio.Task running the agent.
                    Stores it in PENDING_RUNS[call_sid].
                    Returns TwiML: Say "Searching..." + Pause + Redirect /voice/poll.
                    │
                    ▼
   /voice/poll ── if task done: Say reply, optionally Hangup.
                  if not done: Pause + Redirect back to /voice/poll.
                  Twilio's per-webhook 15s timeout never elapses because
                  each /voice/poll returns in milliseconds.

Limits and tradeoffs:
  • In-memory state (PENDING_RUNS, CALL_LOCALE) survives the process but not
    a restart. Fine for hackathon scope. Production would put it in Redis or
    Firestore.
  • The agent's `await_verifier` LONG-RUNNING tool blocks for up to 30 min
    waiting for a human verifier. Twilio's hard maximum call duration is 4
    hours, but holding a caller for more than ~3 minutes is rude. The voice
    handler caps the polling at 90s; if the verifier hasn't decided by then,
    we say "we're still searching, we'll text you" and hang up. SMS dispatch
    via dispatch_notification fires later when the verifier finally decides.

Run locally:
    # In one terminal:
    uv run uvicorn voice_gateway.server:app --reload --port 5001
    # In another, expose to Twilio via ngrok:
    ngrok http 5001
    # Then set the public URL as the Voice webhook on your Twilio number:
    #   https://<ngrok>.ngrok.io/voice/incoming   (HTTP POST)
"""
from __future__ import annotations

import asyncio
import os
import secrets
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import Response

load_dotenv(".env.local")

app = FastAPI(title="DisasterLens Voice Gateway")

# ── In-memory state ──────────────────────────────────────────────────────
# CALL_LOCALE: per-call locale picked by the DTMF IVR. Used by /voice/speech
# to set the STT language and by /voice/poll to set the TTS voice/language.
CALL_LOCALE: dict[str, str] = {}
# PENDING_RUNS: call_sid → asyncio.Task[dict] running the agent. The Task's
# result is the run_query_collect output. We poll the .done() and read the
# .result() when it's true.
PENDING_RUNS: dict[str, asyncio.Task] = {}
# Cap on how many /voice/poll redirects we serve before giving up and
# moving the caller to "we'll text you" terminal state.
POLL_LIMIT = int(os.environ.get("VOICE_POLL_LIMIT", "10"))  # 10 × 8s = 80s
POLL_COUNT: dict[str, int] = {}

# ── Locale config ────────────────────────────────────────────────────────
# Twilio Gather speech language codes — these are BCP-47 with a regional
# subtag. The agent's language code is ISO 639-1 (es, ar, ...). Map both ways.
DTMF_TO_LOCALE: dict[str, str] = {
    "1": "en", "2": "es", "3": "ar", "4": "vi",
}
LOCALE_BCP47: dict[str, str] = {
    "en": "en-US", "es": "es-MX", "ar": "ar-SA", "vi": "vi-VN",
}
LOCALE_TTS_VOICE: dict[str, str] = {
    # Twilio's Polly voices that handle these locales naturally
    "en": "Polly.Joanna",
    "es": "Polly.Lupe",     # es-US neural
    "ar": "Polly.Zeina",    # ar Arabic
    "vi": "Polly.Joanna",   # Twilio Polly doesn't have Vietnamese; fallback to en speaker
}
GREETING = {
    "en": "Hello. Please describe the person you are looking for after the tone, in English.",
    "es": "Hola. Por favor describa a la persona que busca, en español.",
    "ar": "مرحبًا. الرجاء وصف الشخص الذي تبحث عنه باللغة العربية.",
    "vi": "Xin chào. Vui lòng mô tả người bạn đang tìm bằng tiếng Việt.",
}
SEARCHING = {
    "en": "Thank you. We are searching shelter rosters now. Please hold.",
    "es": "Gracias. Estamos buscando en los registros de refugios. Por favor espere.",
    "ar": "شكرًا. نبحث الآن في سجلات الملاجئ. يرجى الانتظار.",
    "vi": "Cảm ơn. Chúng tôi đang tìm trong các danh sách trại tạm trú. Vui lòng chờ.",
}
GIVE_UP = {
    "en": "We are still searching. We will send you a text message when we have an update. Goodbye.",
    "es": "Aún estamos buscando. Le enviaremos un mensaje de texto cuando tengamos una actualización. Adiós.",
    "ar": "ما زلنا نبحث. سنرسل لك رسالة نصية عندما نحصل على تحديث. مع السلامة.",
    "vi": "Chúng tôi vẫn đang tìm. Chúng tôi sẽ gửi tin nhắn khi có cập nhật. Tạm biệt.",
}


def _xml(body: str) -> Response:
    """Return TwiML with the right content-type."""
    payload = f'<?xml version="1.0" encoding="UTF-8"?>{body}'
    return Response(content=payload, media_type="application/xml")


def _say(locale: str, text: str) -> str:
    voice = LOCALE_TTS_VOICE.get(locale, "Polly.Joanna")
    bcp = LOCALE_BCP47.get(locale, "en-US")
    # XML-escape the body — Twilio's TwiML doesn't tolerate raw `<` or `&`.
    safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return f'<Say voice="{voice}" language="{bcp}">{safe}</Say>'


@app.post("/voice/incoming")
async def incoming() -> Response:
    """First webhook hit when a call comes in."""
    twiml = (
        "<Response>"
        '<Gather input="dtmf" numDigits="1" timeout="6" action="/voice/lang" method="POST">'
        '<Say voice="Polly.Joanna" language="en-US">'
        "DisasterLens reunification line. "
        "Press 1 for English, 2 for Spanish, 3 for Arabic, 4 for Vietnamese."
        "</Say>"
        "</Gather>"
        # Fallback if they don't press anything:
        '<Say voice="Polly.Joanna" language="en-US">No selection received. Goodbye.</Say>'
        "<Hangup/>"
        "</Response>"
    )
    return _xml(twiml)


@app.post("/voice/lang")
async def lang_picker(
    CallSid: str = Form(...),
    Digits: str = Form(""),
) -> Response:
    locale = DTMF_TO_LOCALE.get(Digits, "en")
    CALL_LOCALE[CallSid] = locale
    POLL_COUNT[CallSid] = 0
    bcp = LOCALE_BCP47[locale]
    twiml = (
        "<Response>"
        + _say(locale, GREETING[locale])
        + f'<Gather input="speech" language="{bcp}" speechTimeout="auto" '
          f'action="/voice/speech" method="POST"><Pause length="1"/></Gather>'
        + _say(locale, "We did not hear anything. Goodbye.")
        + "<Hangup/>"
        + "</Response>"
    )
    return _xml(twiml)


@app.post("/voice/speech")
async def speech(
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
    From: str = Form(""),
) -> Response:
    locale = CALL_LOCALE.get(CallSid, "en")
    transcript = (SpeechResult or "").strip()

    if not transcript:
        twiml = (
            "<Response>"
            + _say(locale, "We did not catch that. Goodbye.")
            + "<Hangup/></Response>"
        )
        return _xml(twiml)

    # Kick off the agent run as a background task. Lazy-import to keep this
    # module importable without ADK creds (the Twilio webhook itself doesn't
    # need them; only the agent does).
    from agent.main import run_query_collect

    # The agent expects the seeker's text; we tell it the caller is on the
    # phone and stamp the From number so dispatch_notification can SMS it.
    enriched = (
        f"[Channel: phone] [Caller-PhoneNumber: {From}] "
        f"[Seeker-Language: {locale}]\n\n{transcript}"
    )
    task = asyncio.create_task(run_query_collect(
        enriched,
        user_id=f"voice_{From or 'anon'}",
        session_id=CallSid,
        emit_to_stdout=False,
    ))
    PENDING_RUNS[CallSid] = task

    twiml = (
        "<Response>"
        + _say(locale, SEARCHING[locale])
        + '<Pause length="6"/>'
        '<Redirect method="POST">/voice/poll</Redirect>'
        "</Response>"
    )
    return _xml(twiml)


@app.post("/voice/poll")
async def poll(CallSid: str = Form(...)) -> Response:
    locale = CALL_LOCALE.get(CallSid, "en")
    task = PENDING_RUNS.get(CallSid)
    POLL_COUNT[CallSid] = POLL_COUNT.get(CallSid, 0) + 1

    if not task:
        # Lost state (restart?) — politely terminate.
        twiml = (
            "<Response>" + _say(locale, GIVE_UP[locale]) + "<Hangup/></Response>"
        )
        return _xml(twiml)

    if task.done():
        try:
            result = task.result()
            reply = (result.get("reply") or "").strip()
        except Exception as e:
            reply = ""
            print(f"[voice] agent task raised: {e}")
        # Twilio's <Say> handles long text but rambles. Cap to ~600 chars.
        reply = reply[:600] if reply else (
            "We could not find a confident match. We will keep searching and "
            "text you when something turns up."
        )
        # Clean up
        PENDING_RUNS.pop(CallSid, None)
        twiml = (
            "<Response>"
            + _say(locale, reply)
            + '<Pause length="1"/>'
            + _say(locale, "Goodbye.")
            + "<Hangup/></Response>"
        )
        return _xml(twiml)

    if POLL_COUNT.get(CallSid, 0) >= POLL_LIMIT:
        # Cap reached — say goodbye, the SMS path will catch up later when
        # the agent eventually finishes and dispatch_notification fires.
        twiml = (
            "<Response>" + _say(locale, GIVE_UP[locale]) + "<Hangup/></Response>"
        )
        return _xml(twiml)

    # Still working — pause, then come back.
    twiml = (
        "<Response>"
        '<Pause length="6"/>'
        '<Redirect method="POST">/voice/poll</Redirect>'
        "</Response>"
    )
    return _xml(twiml)


# ── Health + diagnostics ─────────────────────────────────────────────────

@app.get("/voice/health")
def health() -> dict:
    return {
        "ok": True,
        "pending_calls": len(PENDING_RUNS),
        "tracked_locales": len(CALL_LOCALE),
    }


# ── SMS helper for dispatch_notification ─────────────────────────────────
# Imported by agent/tools/notify.py when the TWILIO_* env vars are present.
# Kept here so the entire telco surface is one file.

def send_sms(*, to: str, body: str) -> dict:
    """Send an SMS via Twilio's REST API. Returns {ok, sid, error}.

    Activates only when TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN +
    TWILIO_FROM_NUMBER are all set. Otherwise returns {ok: False, error: ...}
    so the caller falls back to the mock-banner dispatch path.
    """
    import httpx

    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_num = os.environ.get("TWILIO_FROM_NUMBER")
    if not (sid and token and from_num):
        return {"ok": False, "error": "TWILIO_* env vars not set; SMS skipped"}

    if not to or not to.startswith("+"):
        return {"ok": False, "error": f"invalid 'to' number {to!r} (must start with +)"}

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    try:
        resp = httpx.post(
            url,
            data={"From": from_num, "To": to, "Body": body[:1500]},  # SMS hard cap is 1600
            auth=(sid, token),
            timeout=10,
        )
    except Exception as e:
        return {"ok": False, "error": f"network: {type(e).__name__}: {e}"}
    if resp.status_code >= 300:
        return {"ok": False, "error": f"twilio HTTP {resp.status_code}: {resp.text[:200]}"}
    return {"ok": True, "sid": resp.json().get("sid"), "to": to}


# ── Sanity check on import ───────────────────────────────────────────────
_SANITY_LOCALES: tuple[Literal["en", "es", "ar", "vi"], ...] = ("en", "es", "ar", "vi")
for _loc in _SANITY_LOCALES:
    assert _loc in GREETING and _loc in SEARCHING and _loc in GIVE_UP
