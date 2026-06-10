"""Reset all DisasterLens demo state to a clean slate, and optionally
pre-stage a guaranteed minor pending decision for the recording.

Use this BETWEEN recording takes (or before starting one) so that:
  • The verifier UI queue is empty — nothing left over from a prior run
  • The dispatched-notifications history doesn't show stale messages
  • The cost-stats counter reflects only the run you're about to record
  • rc_0001 (Carlos Martínez's case) doesn't have a long list of additional
    seekers from earlier test runs
  • Any `rc_live_*` cases created by previous agent runs (which would cause
    dedup to fire on the next query for the same subject) are deleted

What this DOES touch:
  • Firestore  `pending_decisions/*`              — DELETE ALL
  • Firestore  `dispatched_notifications/*`       — DELETE ALL
  • Elastic    `reunification_cases/rc_0001`      — clear additional_seekers
  • Elastic    `reunification_cases/rc_live_*`    — DELETE ALL (agent-created cases)
  • Cloud Run  POST /api/cost-stats/reset         — zero the counters
  • (Optional with --stage) Firestore             — write a guaranteed
    Carlos Mendoza (age 8, minor) pending decision into the queue so the
    verifier-gate beat is ready to demo on camera without depending on
    the agent's confidence-reasoning escalation behavior

What this does NOT touch:
  • The shelter_rosters / missing_person_reports / social_reports indices —
    leaving the synthetic data intact
  • Pre-seeded reunification_cases (rc_0001 through rc_0030 from the
    synthetic data generator)

Run:
    uv run python -m scripts.reset_demo_state                   # clean slate, no staging
    uv run python -m scripts.reset_demo_state --stage           # clean + stage Carlos Mendoza
    uv run python -m scripts.reset_demo_state --dry-run         # preview, don't change
    uv run python -m scripts.reset_demo_state --stage --dry-run # both
"""
from __future__ import annotations

import argparse
import os
import sys

import httpx
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from google.cloud import firestore

load_dotenv(".env.local")

DEPLOYED_BASE_URL = os.environ.get(
    "DEPLOYED_BASE_URL",
    "https://verifier-ui-908473162651.us-central1.run.app",
)


def _wipe_collection(fs: firestore.Client, name: str, dry_run: bool) -> int:
    docs = list(fs.collection(name).stream())
    if dry_run:
        for d in docs[:5]:
            print(f"    would delete: {name}/{d.id}")
        if len(docs) > 5:
            print(f"    ... and {len(docs) - 5} more")
        return len(docs)
    for d in docs:
        d.reference.delete()
    return len(docs)


def _wipe_live_cases(es: Elasticsearch, dry_run: bool) -> int:
    """Delete every reunification_case whose case_id starts with 'rc_live_'.
    These are cases the Coordinator's create_reunification_case skill opened
    during prior agent runs. Leaving them around would cause check_existing_case
    to dedup-hit on retries of the same subject."""
    body = {"query": {"prefix": {"case_id": "rc_live_"}}, "size": 200,
            "_source": ["case_id"]}
    try:
        hits = es.search(index="reunification_cases", body=body).get("hits", {}).get("hits", [])
    except Exception as e:
        print(f"    (search failed: {e})")
        return 0
    if dry_run:
        for h in hits[:5]:
            print(f"    would delete: reunification_cases/{h['_id']}")
        if len(hits) > 5:
            print(f"    ... and {len(hits) - 5} more")
        return len(hits)
    for h in hits:
        try:
            es.delete(index="reunification_cases", id=h["_id"])
        except Exception:
            pass
    return len(hits)


def _stage_minor_decision(fs: firestore.Client, dry_run: bool) -> str | None:
    """Drop a guaranteed Carlos Mendoza (age 8, minor) pending decision into
    Firestore so the verifier-gate beat is reproducible on camera regardless
    of how the agent's confidence reasoning lands. Uses the same doc shape
    as agent.tools.verifier.await_verifier writes."""
    from datetime import datetime, timezone
    from uuid import uuid4
    decision_id = f"dec_demo_{uuid4().hex[:10]}"
    doc = {
        "decision_id": decision_id,
        "status": "pending",
        "candidate_name": "Carlos Mendoza",
        "candidate_shelter": "sh_george_r_brown",
        "candidate_person_id": "sr_demo_carlos_m",
        "candidate_age": 8,
        "candidate_photo_url": "https://api.dicebear.com/9.x/fun-emoji/svg?seed=f_024",
        "seeker_photo_url": None,
        "photo_match_summary": None,
        "confidence": 0.92,
        "evidence": (
            "Name exact match, age match (8), school affiliation consistent "
            "(Hobby Elementary), distinguishing features confirmed (blue "
            "Spider-Man backpack, missing front teeth)."
        ),
        "seeker_query": (
            "I am a teacher looking for one of my students, Carlos Mendoza, "
            "age 8, second grade at Hobby Elementary. He had his blue "
            "Spider-Man backpack and is missing his two front teeth."
        ),
        "seeker_language": "en",
        "seeker_location_text": "Hobby Elementary",
        "seeker_location": {"lat": 29.6611, "lon": -95.2547},
        "disclosure_consent": True,
        "is_minor": True,
        "guardian_verified": None,
        "created_at": datetime.now(timezone.utc),
        "decision": None,
        "verifier_id": None,
        "verifier_note": None,
        "decided_at": None,
    }
    if dry_run:
        print(f"    would stage: pending_decisions/{decision_id}  "
              f"(candidate=Carlos Mendoza, age=8, is_minor=true)")
        return None
    fs.collection("pending_decisions").document(decision_id).set(doc)
    return decision_id


def _reset_rc_0001(es: Elasticsearch, dry_run: bool) -> int:
    try:
        snap = es.get(index="reunification_cases", id="rc_0001")
    except Exception as e:
        print(f"    (rc_0001 not found, skipping: {e})")
        return 0
    n = len((snap.get("_source") or {}).get("additional_seekers") or [])
    if dry_run:
        print(f"    would clear {n} additional_seekers from rc_0001")
        return n
    if n > 0:
        es.update(index="reunification_cases", id="rc_0001",
                  body={"doc": {"additional_seekers": []}})
    return n


def _reset_cost_stats(dry_run: bool) -> bool:
    url = f"{DEPLOYED_BASE_URL}/api/cost-stats/reset"
    if dry_run:
        print(f"    would POST {url}")
        return True
    try:
        r = httpx.post(url, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"    (cost-stats reset failed: {e})")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted/reset without doing it")
    parser.add_argument("--stage", action="store_true",
                        help="After reset, also drop a guaranteed Carlos Mendoza "
                             "(age 8, minor) pending decision into the verifier "
                             "queue — perfect for the minor-gate demo beat")
    args = parser.parse_args()

    proj = os.environ.get("GCP_PROJECT_ID")
    if not proj:
        sys.exit("✗ GCP_PROJECT_ID not set in env / .env.local")

    print(f"{'DRY-RUN: ' if args.dry_run else ''}resetting demo state on project={proj}")
    print()

    fs = firestore.Client(project=proj)
    es = Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=15,
    )

    print("▸ Firestore: pending_decisions")
    n_pending = _wipe_collection(fs, "pending_decisions", args.dry_run)
    print(f"  {'would delete' if args.dry_run else 'deleted'}: {n_pending} doc(s)")

    print()
    print("▸ Firestore: dispatched_notifications")
    n_dispatched = _wipe_collection(fs, "dispatched_notifications", args.dry_run)
    print(f"  {'would delete' if args.dry_run else 'deleted'}: {n_dispatched} doc(s)")

    print()
    print("▸ Elastic: rc_0001.additional_seekers")
    n_seekers = _reset_rc_0001(es, args.dry_run)
    print(f"  {'would clear' if args.dry_run else 'cleared'}: {n_seekers} seeker(s)")

    print()
    print("▸ Elastic: reunification_cases/rc_live_* (agent-created cases that block dedup retries)")
    n_live = _wipe_live_cases(es, args.dry_run)
    print(f"  {'would delete' if args.dry_run else 'deleted'}: {n_live} case(s)")

    print()
    print(f"▸ Cloud Run: /api/cost-stats/reset  ({DEPLOYED_BASE_URL})")
    ok = _reset_cost_stats(args.dry_run)
    print(f"  {'OK' if ok else 'FAILED'}")

    if args.stage:
        print()
        print("▸ Stage: pending_decisions for Carlos Mendoza (age 8, minor)")
        staged_id = _stage_minor_decision(fs, args.dry_run)
        if staged_id:
            print(f"  staged: {staged_id}")

    print()
    if args.dry_run:
        print("(dry-run — nothing was actually changed)")
    else:
        print("✓ demo state reset to clean slate"
              + (" + minor decision staged" if args.stage else ""))
        if args.stage:
            print("  Open the verifier UI's 'Pending Decisions' tab — Carlos Mendoza")
            print("  appears within 1.5s with the yellow MINOR · age 8 badge.")


if __name__ == "__main__":
    main()
