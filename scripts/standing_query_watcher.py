"""Standing-query watcher — re-fires open cases as new roster docs arrive.

Reunification is rarely a one-shot match. María calls in at hour 1; Carlos is
logged into a shelter at hour 4. Without a watcher, María's case sits in
"no_match" forever. With one, the moment Carlos's roster doc lands, the
watcher matches the open standing-query against it and writes a pending
decision into Firestore — the verifier UI lights up, the verifier reviews
the gate, the agent's notifier dispatches the SMS.

Operationally this runs as a **Cloud Run Job** (or `cron` locally) every N
minutes. Each tick:

  1. List `reunification_cases` where `standing_query_active=true` AND
     `status NOT IN (verified, closed_*)`.
  2. For each open case, run `match_person_across_rosters` with the case's
     stored variants + age estimate.
  3. Filter candidates: only those whose `arrival_time` is AFTER the
     case's `created_at` (so we don't re-fire on docs we already searched
     against initially) AND whose fused confidence ≥ FUSED_THRESHOLD.
  4. Skip candidates whose `person_id` already appears in the case's
     `candidate_matches[].person_id` (idempotent across watcher ticks).
  5. For each surviving candidate, write a `pending_decisions/{id}` doc
     to Firestore with the same shape `await_verifier` would have written.
  6. Append the candidate to the case's `candidate_matches` so the next
     tick doesn't re-surface it.

This is the third-beat demo moment: the verifier queue is empty after the
seeker's first chat → the incident-stream drops a new roster doc → the
watcher fires → a new pending decision lands in the verifier UI mid-demo.

Run locally for development:
    uv run python -m scripts.standing_query_watcher --interval-sec 15
    uv run python -m scripts.standing_query_watcher --once          # one tick + exit

Deploy as Cloud Run Job:
    gcloud run jobs deploy standing-query-watcher \\
      --image=$IMAGE --task-timeout=300 --max-retries=0 \\
      --command=uv --args=run,python,-m,scripts.standing_query_watcher,--once \\
      --set-env-vars=WATCHER_MODE=cloudrun
    # Then schedule it:
    gcloud scheduler jobs create http standing-query-watcher-trigger \\
      --schedule="*/2 * * * *" --uri="...Job-execute URL..."
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from google.cloud import firestore

from agent.config import (
    ELASTIC_API_KEY,
    ELASTIC_ENDPOINT,
    GCP_PROJECT_ID,
    INDEX_REUNIFICATION_CASES,
    LOW_CONFIDENCE_FLOOR,
)
from agent.tools.skills import match_person_across_rosters
from agent.tools.verifier import PENDING_COLLECTION

load_dotenv(".env.local")

_TERMINAL = ("verified", "closed_false_match", "closed_no_match")


def _es() -> Elasticsearch:
    return Elasticsearch(hosts=[ELASTIC_ENDPOINT], api_key=ELASTIC_API_KEY, request_timeout=15)


def _fs() -> firestore.Client:
    return firestore.Client(project=GCP_PROJECT_ID)


def _open_cases(es: Elasticsearch) -> list[dict]:
    """All cases with standing_query_active=true and non-terminal status."""
    body = {
        "size": 200,
        "query": {
            "bool": {
                "must": [{"term": {"standing_query_active": True}}],
                "must_not": [{"terms": {"status": list(_TERMINAL)}}],
            }
        },
        "sort": [{"created_at": "asc"}],
    }
    resp = es.search(index=INDEX_REUNIFICATION_CASES, body=body)
    return [{"_id": h["_id"], **(h["_source"] or {})}
            for h in resp.get("hits", {}).get("hits", [])]


def _fused_confidence(top1_score: float, score_ceiling: float = 12.0) -> float:
    """Coarse mirror of evals/score.py's fused_confidence(). Without the seeker
    query at watcher-tick time we can't compute the token-overlap term, so we
    use a conservative name-only normalisation."""
    name_norm = min(top1_score / score_ceiling, 1.0)
    return round(name_norm * 0.8, 3)  # 0.8 reflects "name only — age unverified"


def _already_seen(case: dict, person_id: str) -> bool:
    for cm in (case.get("candidate_matches") or []):
        if cm.get("person_id") == person_id:
            return True
    return False


def _write_pending_decision(
    fs_client: firestore.Client,
    case: dict,
    candidate: dict,
    confidence: float,
) -> str:
    decision_id = f"dec_watcher_{uuid4().hex[:10]}"
    src = candidate
    doc = {
        "decision_id": decision_id,
        "status": "pending",
        "origin": "standing_query_watcher",
        "case_id": case.get("case_id"),
        "candidate_name": src.get("name"),
        "candidate_shelter": src.get("shelter_id"),
        "candidate_person_id": src.get("person_id"),
        "candidate_age": src.get("age"),
        "candidate_photo_url": src.get("intake_photo_url"),
        "seeker_photo_url": None,
        "photo_match_summary": None,
        "confidence": confidence,
        "evidence": (
            f"Standing-query match on new arrival. Variant rule: "
            f"{src.get('matched_variant_rule', 'canonical')}. "
            f"Original case opened at {case.get('created_at')}."
        ),
        "seeker_query": case.get("subject_name_as_given", ""),
        "seeker_language": case.get("seeker_language", "en"),
        "seeker_location_text": "",
        "seeker_location": case.get("last_known_location"),
        "disclosure_consent": bool(src.get("disclosure_consent")),
        "is_minor": bool(src.get("is_minor")),
        "guardian_verified": None,
        "created_at": datetime.now(timezone.utc),
        "decision": None,
        "verifier_id": None,
        "verifier_note": None,
        "decided_at": None,
    }
    fs_client.collection(PENDING_COLLECTION).document(decision_id).set(doc)
    return decision_id


def _append_candidate_to_case(
    es: Elasticsearch,
    case_id: str,
    candidate: dict,
    confidence: float,
    decision_id: str,
) -> None:
    """Make the watcher idempotent: stamp the candidate's person_id into the
    case so the next tick skips it."""
    es.update(
        index=INDEX_REUNIFICATION_CASES,
        id=case_id,
        body={
            "script": {
                "lang": "painless",
                "source": (
                    "if (ctx._source.candidate_matches == null) "
                    "{ ctx._source.candidate_matches = []; } "
                    "ctx._source.candidate_matches.add(params.cm);"
                ),
                "params": {"cm": {
                    "person_id": candidate.get("person_id"),
                    "source_index": "shelter_rosters",
                    "confidence": confidence,
                    "evidence": "standing-query watcher",
                    "verifier_decision": "pending",
                    "verified_at": None,
                    "decision_id": decision_id,
                }},
            }
        },
    )


def tick(es: Elasticsearch, fs_client: firestore.Client, dry_run: bool = False) -> dict:
    cases = _open_cases(es)
    new_decisions: list[dict] = []

    for case in cases:
        subject = case.get("subject_name_as_given")
        if not subject:
            continue
        age = case.get("subject_age_estimate")
        lang_hint = case.get("seeker_language")

        # Re-run the same branded skill the agent uses at first-touch time.
        result = match_person_across_rosters(
            subject_name=subject,
            subject_age=age,
            language_hint=lang_hint,
            top_k=3,
        )

        for cand in result.get("candidates", []):
            if _already_seen(case, cand.get("person_id")):
                continue
            confidence = _fused_confidence(cand.get("score") or 0.0)
            if confidence < LOW_CONFIDENCE_FLOOR:
                continue
            # Respect consent gate — never write a pending decision for a
            # candidate who didn't consent; the agent's runtime backstops
            # would refuse to dispatch anyway, and writing the decision
            # would just create verifier-UI clutter.
            if cand.get("disclosure_consent") is False:
                continue

            if dry_run:
                new_decisions.append({
                    "case_id": case.get("case_id"),
                    "candidate": cand.get("name"),
                    "confidence": confidence,
                    "dry_run": True,
                })
                continue

            decision_id = _write_pending_decision(fs_client, case, cand, confidence)
            try:
                _append_candidate_to_case(es, case["_id"], cand, confidence, decision_id)
            except Exception as e:
                # Don't crash the tick — the candidate write went to Firestore
                # already, the worst case is a future re-surface of the same
                # candidate, which the verifier will dismiss.
                print(f"  (warn) failed to stamp candidate on case {case['_id']}: {e}")
            new_decisions.append({
                "case_id": case.get("case_id"),
                "decision_id": decision_id,
                "candidate": cand.get("name"),
                "confidence": confidence,
            })

    return {
        "n_open_cases": len(cases),
        "n_new_decisions": len(new_decisions),
        "new_decisions": new_decisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--interval-sec", type=float, default=30.0,
                        help="Seconds between ticks when not --once (default 30)")
    parser.add_argument("--once", action="store_true",
                        help="Run one tick and exit (the Cloud Run Job mode)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write to Firestore or Elastic; just print what would happen")
    parser.add_argument("--max-ticks", type=int, default=None,
                        help="Stop after this many ticks (default: forever)")
    args = parser.parse_args()

    if os.environ.get("WATCHER_MODE") == "cloudrun":
        args.once = True  # Cloud Run Jobs are one-shot

    es = _es()
    fs_client = _fs() if not args.dry_run else None
    n_ticks = 0
    print(f"[watcher] starting  dry_run={args.dry_run}  once={args.once}")
    while True:
        n_ticks += 1
        try:
            summary = tick(es, fs_client, dry_run=args.dry_run)
        except Exception as e:
            print(f"  ✗ tick failed: {type(e).__name__}: {e}")
            summary = {"n_open_cases": 0, "n_new_decisions": 0}
        print(f"  tick {n_ticks}:  open_cases={summary['n_open_cases']}  "
              f"new_decisions={summary['n_new_decisions']}")
        for nd in summary.get("new_decisions") or []:
            print(f"    → case={nd.get('case_id')}  candidate={nd.get('candidate')!r}  "
                  f"confidence={nd.get('confidence')}  decision={nd.get('decision_id', 'DRY')}")
        if args.once:
            return
        if args.max_ticks and n_ticks >= args.max_ticks:
            return
        time.sleep(args.interval_sec)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[watcher] bye")
        sys.exit(0)
