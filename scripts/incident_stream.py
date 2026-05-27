"""Live incident-mode stream — drips new shelter-roster docs into Elastic
on a schedule so the demo video can show the standing-query mechanism firing
in real time.

Storyboard:
  1. Start the agent + verifier UI.
  2. Pre-load a `reunification_cases` doc with `standing_query_active=true`
     for a subject whose match will arrive 30s into the demo (e.g. María's
     Carlos — exists in personas.STRESS_PERSONAS).
  3. Run this script alongside the demo. Every N seconds it inserts a new
     roster doc — either fresh filler personas (noise) or, at the scripted
     beat, one of the stress-persona variants that closes a standing case.
  4. The map and the verifier queue light up in real time. Three minutes of
     video, but on-screen something is happening continuously.

Designed to run BOTH locally (cron-style background process) and as a
Cloud Run Job (set `INCIDENT_STREAM_MODE=cloudrun`). Idempotent: a watermark
file pins which personas have already been streamed so reruns don't
double-write the same doc.

Run locally:
    uv run python -m scripts.incident_stream --period-sec 8 --max-docs 12
    uv run python -m scripts.incident_stream --hero-only      # just the demo-beat docs
    uv run python -m scripts.incident_stream --reset          # clear streamed flag

Deploy as Cloud Run Job (per design.md §11):
    gcloud run jobs create incident-stream \\
      --image=$IMAGE --task-timeout=10m --max-retries=1 \\
      --set-env-vars=INCIDENT_STREAM_MODE=cloudrun
    gcloud run jobs execute incident-stream --wait
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from data.generate_synthetic import avatar_url
from data.personas import FILLER_PERSONAS, SHELTERS, STRESS_PERSONAS, Persona
from data.variants import expand

load_dotenv(".env.local")

INDEX = "shelter_rosters"
WATERMARK = Path(__file__).resolve().parent / ".incident_stream_watermark.json"

# Demo-beat personas: the ones whose "newly arrived" roster doc closes the
# standing query for an existing reunification case. Order matters — list
# them in the order you want the verifier queue to populate.
_HERO_PERSONA_IDS = ("p_carlos_001", "p_mohammed_001", "p_nguyen_001")


def _client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=15,
    )


def _load_watermark() -> dict:
    if WATERMARK.exists():
        try:
            return json.loads(WATERMARK.read_text())
        except Exception:
            return {}
    return {}


def _save_watermark(data: dict) -> None:
    WATERMARK.write_text(json.dumps(data, indent=2))


def _build_roster_doc(
    persona: Persona,
    shelter: dict,
    rng: random.Random,
    variant_rule: str | None = None,
) -> dict:
    """Construct a single roster doc, matching the schema in
    data/generate_synthetic.py exactly (including the new disclosure_consent
    and is_minor fields)."""
    # Choose a variant of the canonical name — stresses the fuzzy stack on
    # the live insertion. Falls back to canonical when there are no variants.
    variants = list(expand(persona.canonical_name))
    if variant_rule:
        matches = [v for v in variants if v.rule == variant_rule]
        chosen = matches[0] if matches else None
    else:
        chosen = rng.choice(variants) if variants else None
    surface_name = chosen.surface_form if chosen else persona.canonical_name
    rule = chosen.rule if chosen else "canonical"
    surface_variants = sorted({v.surface_form for v in expand(surface_name)})

    return {
        "person_id": f"sr_live_{persona.person_id}_{int(time.time())}",
        "shelter_id": shelter["shelter_id"],
        "name": surface_name,
        "name_variants": surface_variants,
        "age": persona.age,
        "is_minor": persona.age < 18,
        "language_spoken": persona.language_spoken,
        "arrival_time": datetime.now(timezone.utc).isoformat(),
        "school_or_employer": persona.school_or_employer,
        "distinguishing_features": persona.distinguishing_features,
        "disclosure_consent": True,  # streamed docs all consent — keeps the
                                     # demo trace clean. Real intake would
                                     # vary.
        "intake_photo_url": avatar_url(persona.person_id, persona.age),
        "shelter_location": {
            "lat": float(shelter["lat"]) + rng.uniform(-0.001, 0.001),
            "lon": float(shelter["lon"]) + rng.uniform(-0.001, 0.001),
        },
        # Streaming marker — distinguishes a live-drip insert from a bulk-load
        # entry in the ES indexes UI during the demo.
        "_source_kind": "incident_stream",
        "_streamed_rule": rule,
    }, rule


def _candidate_personas(
    hero_only: bool,
    streamed: set[str],
) -> list[Persona]:
    """Returns the streaming queue in order. Hero personas first (so the
    verifier queue populates with the dramatic matches), then noise filler."""
    out: list[Persona] = []
    hero_by_id = {p.person_id: p for p in STRESS_PERSONAS}
    for pid in _HERO_PERSONA_IDS:
        if pid in hero_by_id and pid not in streamed:
            out.append(hero_by_id[pid])
    if hero_only:
        return out
    # Then fillers, skipping any already streamed
    for p in FILLER_PERSONAS:
        if p.person_id not in streamed:
            out.append(p)
    return out


def stream(
    *,
    period_sec: float,
    max_docs: int | None,
    hero_only: bool,
    dry_run: bool,
) -> int:
    rng = random.Random(int(time.time()))
    es = _client() if not dry_run else None
    wm = _load_watermark()
    streamed: set[str] = set(wm.get("streamed_persona_ids", []))

    queue = _candidate_personas(hero_only, streamed)
    if not queue:
        print("(nothing to stream — watermark says all personas already inserted; "
              "use --reset to clear)")
        return 0

    if max_docs is not None:
        queue = queue[:max_docs]

    print(f"streaming {len(queue)} roster docs at {period_sec:.1f}s intervals "
          f"{'(DRY RUN)' if dry_run else ''}")
    for i, persona in enumerate(queue, start=1):
        shelter = rng.choice(SHELTERS)
        # For hero personas we deliberately pick a non-canonical variant so the
        # fuzzy stack has to work — that's the moment the demo wants on screen.
        rule = "fold_diacritics" if persona.person_id == "p_carlos_001" else None
        doc, used_rule = _build_roster_doc(persona, shelter, rng, variant_rule=rule)

        print(f"  [{i}/{len(queue)}] {persona.person_id:18}  "
              f"name={doc['name']!r}  rule={used_rule}  shelter={shelter['shelter_id']}")
        if not dry_run:
            es.index(index=INDEX, id=doc["person_id"], document=doc, refresh=True)
            streamed.add(persona.person_id)
            wm["streamed_persona_ids"] = sorted(streamed)
            wm["last_streamed_at"] = datetime.now(timezone.utc).isoformat()
            _save_watermark(wm)
        if i < len(queue):
            time.sleep(period_sec)
    return 0


def reset_watermark() -> None:
    if WATERMARK.exists():
        WATERMARK.unlink()
        print(f"  ✓ cleared {WATERMARK.name}")
    else:
        print(f"  (no watermark to clear)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--period-sec", type=float, default=8.0,
                        help="Seconds between insertions (default 8.0)")
    parser.add_argument("--max-docs", type=int, default=None,
                        help="Stop after this many insertions (default: drain the queue)")
    parser.add_argument("--hero-only", action="store_true",
                        help="Only stream the demo-beat hero personas (3 docs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the docs but don't write to Elastic")
    parser.add_argument("--reset", action="store_true",
                        help="Clear the watermark so all personas restream next run")
    args = parser.parse_args()

    if args.reset:
        reset_watermark()
        return

    # Cloud Run Job override — when running unattended, prefer short period
    # and bounded max-docs unless explicitly overridden.
    if os.environ.get("INCIDENT_STREAM_MODE") == "cloudrun":
        if args.period_sec == 8.0:
            args.period_sec = float(os.environ.get("STREAM_PERIOD_SEC", "8.0"))
        if args.max_docs is None:
            args.max_docs = int(os.environ.get("STREAM_MAX_DOCS", "12"))

    sys.exit(stream(
        period_sec=args.period_sec,
        max_docs=args.max_docs,
        hero_only=args.hero_only,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
