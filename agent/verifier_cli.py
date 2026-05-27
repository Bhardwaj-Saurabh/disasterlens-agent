"""CLI verifier — stands in for the React verifier UI during backend development.

Same Firestore contract as the React UI will use:
  • lists docs in `pending_decisions` where decision is null
  • presents candidate + evidence
  • on y/n input, writes `decision`, `verifier_id`, `decided_at` to the doc
  • the agent's `await_verifier` polling tool sees the field and resumes

Usage (in a SECOND terminal while the agent run is paused):
    uv run python -m agent.verifier_cli                # interactive
    uv run python -m agent.verifier_cli --auto-approve # demo mode: approve everything
    uv run python -m agent.verifier_cli --watch        # keep watching, approve as decisions arrive

Quit with Ctrl-C.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from google.cloud import firestore

from agent.config import GCP_PROJECT_ID, VERIFIER_POLL_INTERVAL_SECONDS
from agent.tools.verifier import PENDING_COLLECTION

VERIFIER_ID = "cli_verifier"


def _client() -> firestore.Client:
    return firestore.Client(project=GCP_PROJECT_ID)


def _print_doc(doc_id: str, data: dict) -> None:
    print()
    print("┌─────────────────────────────────────────────────────────────────────────")
    print(f"│ DECISION REQUEST  {doc_id}")
    print(f"│ confidence:  {data.get('confidence'):.3f}")
    print(f"│ seeker:      {data.get('seeker_query')!r}  ({data.get('seeker_language')})")
    print(f"│ candidate:   {data.get('candidate_name')!r}"
          f"  (age={data.get('candidate_age')})")
    print(f"│   in shelter {data.get('candidate_shelter')}  (person_id={data.get('candidate_person_id')})")
    print(f"│ evidence:    {data.get('evidence')}")
    # Policy gates — surface inline so the verifier can't miss them.
    if data.get("is_minor"):
        print("│ ⚠  POLICY:  candidate is a MINOR — guardian verification required to approve")
    if data.get("disclosure_consent") is False:
        print("│ ⚠  POLICY:  disclosure_consent=False — approval will not dispatch")
    print("└─────────────────────────────────────────────────────────────────────────")


def _record_decision(
    doc_ref,
    decision: str,
    note: str = "",
    guardian_verified: bool | None = None,
) -> None:
    update: dict = {
        "decision": decision,
        "verifier_id": VERIFIER_ID,
        "verifier_note": note,
        "decided_at": datetime.now(timezone.utc),
        "status": "decided",
    }
    if guardian_verified is not None:
        update["guardian_verified"] = guardian_verified
    doc_ref.update(update)
    print(f"  → wrote decision={decision!r}"
          + (f" guardian_verified={guardian_verified}" if guardian_verified is not None else "")
          + "\n")


def list_pending(client: firestore.Client) -> list[firestore.DocumentSnapshot]:
    return [
        d for d in client.collection(PENDING_COLLECTION).where(
            filter=firestore.FieldFilter("decision", "==", None)
        ).stream()
    ]


def process_interactive(snaps: list[firestore.DocumentSnapshot]) -> None:
    for snap in snaps:
        data = snap.to_dict() or {}
        _print_doc(snap.id, data)
        is_minor = bool(data.get("is_minor"))
        consent_withheld = data.get("disclosure_consent") is False
        while True:
            choice = input("  approve / reject / skip / quit  [a/r/s/q]: ").strip().lower()
            if choice in {"a", "approve"}:
                if consent_withheld:
                    print("  ✗ disclosure_consent=False — dispatch will refuse; "
                          "reject or skip instead")
                    continue
                guardian = None
                if is_minor:
                    confirm = input("  Guardian relationship confirmed (school record / "
                                    "photo ID / cross-roster)? [y/N]: ").strip().lower()
                    guardian = confirm in {"y", "yes"}
                    if not guardian:
                        print("  ✗ minor approval requires guardian confirmation — skipping")
                        continue
                note = input("  note (optional): ").strip()
                _record_decision(snap.reference, "approved", note, guardian)
                break
            if choice in {"r", "reject"}:
                note = input("  reason: ").strip()
                _record_decision(snap.reference, "rejected", note)
                break
            if choice in {"s", "skip"}:
                print("  → skipped (will appear again on next poll)\n")
                break
            if choice in {"q", "quit"}:
                sys.exit(0)
            print("  unrecognised — pick a/r/s/q")


def process_auto_approve(snaps: list[firestore.DocumentSnapshot]) -> None:
    for snap in snaps:
        data = snap.to_dict() or {}
        _print_doc(snap.id, data)
        if data.get("disclosure_consent") is False:
            # The auto-approve "demo mode" still respects the consent gate —
            # otherwise the dispatcher would refuse and the demo trace would
            # show a confusing failure on what looks like a happy-path run.
            _record_decision(snap.reference, "rejected",
                             "auto-rejected: disclosure_consent=false (demo mode)")
            continue
        guardian = True if data.get("is_minor") else None
        _record_decision(snap.reference, "approved",
                         "auto-approved (demo mode)", guardian)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-approve every pending decision (demo mode)")
    parser.add_argument("--watch", action="store_true",
                        help="Keep polling for new decisions (otherwise exits after first pass)")
    args = parser.parse_args()

    client = _client()
    handler = process_auto_approve if args.auto_approve else process_interactive

    while True:
        snaps = list_pending(client)
        if snaps:
            print(f"[verifier_cli] {len(snaps)} pending decision(s)")
            handler(snaps)
        elif not args.watch:
            print("[verifier_cli] no pending decisions — exiting (use --watch to keep polling)")
            return
        if not args.watch:
            return
        time.sleep(VERIFIER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[verifier_cli] bye")
