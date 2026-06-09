"""photo_match — Gemini Vision second-opinion comparison of two photos.

When a seeker uploads a photo of the subject AND the candidate roster doc
carries an `intake_photo_url`, the Coordinator calls this tool BEFORE
`await_verifier` to extract a structured similarity assessment. The result
becomes part of the evidence string the verifier sees and is folded into the
agent's confidence score.

Design constraints:
  • This is a SECOND OPINION, not a primary decision input. The verifier
    still owns the call. Photo evidence weight is capped — confidence cannot
    swing more than ±0.15 from photos alone.
  • Avatar-vs-photo cases (synthetic data, demo time) are handled honestly:
    when Gemini reports "this appears to be an illustrated avatar," the tool
    returns `comparable: false` and the agent reverts to text-only matching.
    This is the right behavior for the hackathon synthetic data AND the right
    behavior in production for shelters that don't capture intake photos.
  • No image is persisted by this tool. Inputs are URLs; the call streams
    bytes to Gemini and discards them. The decision doc records the verdict,
    not the bytes.

Model choice: gemini-2.5-flash — Vertex-available, supports multimodal input.
"""
from __future__ import annotations

import json
import re

import httpx

from agent.config import GEMINI_MODEL

# Photo evidence cap on confidence movement. The agent's fused confidence
# already weighs name/age/affiliation — photos add a +/- 0.15 nudge, never
# more. If Gemini says "definitely the same person" the verifier still has
# to confirm.
_PHOTO_CONFIDENCE_CAP = 0.15

_PROMPT = """\
You are comparing two photographs to assess whether they plausibly depict
the same person, in the context of a disaster family-reunification matching
system. You are NOT making a biometric identification — you are providing
one input among many to a human verifier.

Image A is from the SEEKER (a family member looking for their relative).
Image B is the candidate's intake photo from a shelter roster.

Return a strict JSON object with these fields:
{
  "comparable": <bool>,             # false if either image is an avatar,
                                     # illustration, cartoon, or otherwise
                                     # NOT a photograph of a real person
  "same_person_likely": <bool|null>, # null when comparable=false
  "confidence": <float in [0, 1]>,  # 0 = definitely not, 1 = highly likely
  "agreeing_features": [<string>], # short phrases: "approximate age 60-70",
                                     # "grey hair", "glasses", "facial hair"
  "differing_features": [<string>],# short phrases pointing out disagreements
  "notes": "<one-sentence summary, ≤120 chars>"
}

Strict rules:
  • If EITHER image is an illustration / avatar / cartoon / drawing, set
    comparable=false, same_person_likely=null, confidence=0, and explain in
    notes ("Image B appears to be an illustrated avatar; biometric comparison
    not applicable").
  • Do NOT speculate about ethnicity, religion, or socioeconomic status —
    only physically observable features.
  • Do NOT speculate about identity beyond plausibility. Never claim a match
    or non-match definitively.
  • Output JSON ONLY. No prose, no markdown fences.
"""


_JSON_OBJ_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> dict:
    """Lenient JSON extraction — the model occasionally wraps the object in
    a code fence despite the prompt. Pull out the first {...} block."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    m = _JSON_OBJ_RE.search(text)
    if not m:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return json.loads(m.group(0))


def _fetch_image(url: str, timeout: float = 8.0) -> tuple[bytes, str]:
    """Download an image URL → (bytes, mime_type). Lenient about content-type."""
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    mime = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if not mime.startswith("image/"):
        # DiceBear returns image/svg+xml — Gemini accepts svg as image/svg+xml.
        # If the upstream is unhelpful, fall back to JPEG.
        mime = "image/jpeg"
    return resp.content, mime


def photo_match(seeker_photo_url: str, candidate_photo_url: str) -> dict:
    """Compare two photos using Gemini Vision and return a structured similarity
    assessment. Use BEFORE `await_verifier` whenever both URLs are available.

    Args:
        seeker_photo_url: URL of the photo the seeker provided of the subject.
        candidate_photo_url: URL of the candidate's shelter-intake photo
            (the `intake_photo_url` field on the roster doc).

    Returns:
        {
          "comparable": bool,
          "same_person_likely": bool | null,
          "confidence": float in [0, 1],
          "agreeing_features": [str],
          "differing_features": [str],
          "notes": str,
          "confidence_delta": float in [-_PHOTO_CONFIDENCE_CAP, +_PHOTO_CONFIDENCE_CAP],
          # The signed nudge the agent should apply to its fused confidence
          # before calling await_verifier. Positive when same_person_likely
          # is true, negative when false, zero when comparable=false.
        }

        On error (network fail, model refused): returns the same shape with
        `comparable=false` and `notes` explaining the failure mode. The agent
        proceeds as if no photo evidence were available.
    """
    # Lazy-import — keeps the module importable in test contexts that don't
    # have Vertex creds set up.
    from google import genai
    from google.genai import types

    try:
        seeker_bytes, seeker_mime = _fetch_image(seeker_photo_url)
        candidate_bytes, candidate_mime = _fetch_image(candidate_photo_url)
    except Exception as e:
        return {
            "comparable": False,
            "same_person_likely": None,
            "confidence": 0.0,
            "agreeing_features": [],
            "differing_features": [],
            "notes": f"photo fetch failed: {type(e).__name__}",
            "confidence_delta": 0.0,
        }

    from agent.telemetry import tracker
    tracker.record_photo_match()

    client = genai.Client()
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=_PROMPT),
                        types.Part.from_text(text="Image A (seeker):"),
                        types.Part.from_bytes(data=seeker_bytes, mime_type=seeker_mime),
                        types.Part.from_text(text="Image B (candidate intake):"),
                        types.Part.from_bytes(data=candidate_bytes, mime_type=candidate_mime),
                    ],
                ),
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        # Record token usage when the SDK surfaces it (best-effort — the field
        # name varies across SDK versions). Cost telemetry tolerates missing data.
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            tracker.record_llm_call(
                model=GEMINI_MODEL,
                input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
                output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
                purpose="photo_match",
            )
    except Exception as e:
        return {
            "comparable": False,
            "same_person_likely": None,
            "confidence": 0.0,
            "agreeing_features": [],
            "differing_features": [],
            "notes": f"vision call failed: {type(e).__name__}: {str(e)[:80]}",
            "confidence_delta": 0.0,
        }

    text = (getattr(resp, "text", None) or "").strip()
    try:
        parsed = _extract_json(text)
    except Exception as e:
        return {
            "comparable": False,
            "same_person_likely": None,
            "confidence": 0.0,
            "agreeing_features": [],
            "differing_features": [],
            "notes": f"vision output unparseable: {type(e).__name__}",
            "confidence_delta": 0.0,
        }

    # Defensive defaults — the model occasionally omits a field
    out = {
        "comparable": bool(parsed.get("comparable", False)),
        "same_person_likely": parsed.get("same_person_likely"),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "agreeing_features": list(parsed.get("agreeing_features") or [])[:6],
        "differing_features": list(parsed.get("differing_features") or [])[:6],
        "notes": str(parsed.get("notes", ""))[:140],
    }
    # Compute the agent-facing nudge
    if not out["comparable"]:
        out["confidence_delta"] = 0.0
    else:
        sign = +1.0 if out["same_person_likely"] else -1.0
        out["confidence_delta"] = round(sign * _PHOTO_CONFIDENCE_CAP * out["confidence"], 4)
    return out
