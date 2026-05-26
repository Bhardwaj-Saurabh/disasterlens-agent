"""Generate synthetic data for all 4 indices + the eval gold set.

Inputs:
  data/personas.py   — hand-curated persona pool (STRESS + FILLER)
  data/variants.py   — deterministic name-variant generator
  data/embed.py      — client-side embedding via disasterlens_e5

Outputs (data/synthetic/, NDJSON for the bulk API):
  shelter_rosters.ndjson         (~120 docs across 10 shelters)
  missing_person_reports.ndjson  (~50 reports, EN/ES/AR/VI, with description_embedding)
  reunification_cases.ndjson     (30 open seeker queries, mix of statuses)
  social_reports.ndjson          (~80 multilingual mentions, with text_embedding)
  evals/family_pairs.jsonl       (50 gold cases — eval scoreboard input)

Distribution policy:
  • Each STRESS persona appears in 2–3 shelter_rosters, each time as a DIFFERENT
    variant of their canonical name. This is the cross-roster collision the
    hero search has to resolve.
  • Each FILLER persona appears in exactly 1 shelter (no variant collisions).
  • The gold set then asks the agent: "given <seeker_query>, find every entry
    in the data that should match" and the eval scores precision/recall by rule.

Deterministic via fixed RNG seed — same output every run.

Run:
    uv run python -m data.generate_synthetic
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.embed import build_client, embed_many
from data.personas import FILLER_PERSONAS, SHELTERS, STRESS_PERSONAS, Persona
from data.variants import Variant, expand

SEED = 20260526  # demo date, frozen for reproducibility
OUT_DIR = Path(__file__).resolve().parent / "synthetic"
EVALS_DIR = Path(__file__).resolve().parents[1] / "evals"

STORM_START = datetime(2026, 5, 26, 14, 0, tzinfo=timezone.utc)


# ── helpers ───────────────────────────────────────────────────────────────

def random_arrival_time(rng: random.Random) -> str:
    """Arrival times spread over the 12 hours after the storm hits."""
    offset_min = rng.randint(0, 12 * 60)
    return (STORM_START + timedelta(minutes=offset_min)).isoformat()


def jitter_geo(rng: random.Random, lat: float, lon: float) -> dict[str, float]:
    """Add ~100m of jitter so geo-points aren't perfectly stacked at the shelter."""
    return {
        "lat": lat + rng.uniform(-0.001, 0.001),
        "lon": lon + rng.uniform(-0.001, 0.001),
    }


def write_ndjson(path: Path, docs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"  ✓ wrote {path.relative_to(Path.cwd())}  ({len(docs)} docs)")


# ── shelter rosters + gold-pair seeds ────────────────────────────────────

def build_shelter_rosters(rng: random.Random) -> tuple[list[dict], dict[str, list[dict]]]:
    """Returns (roster_docs, persona_to_appearances) where persona_to_appearances[pid]
    is a list of {variant, shelter_id, doc_name} dicts — used to build gold pairs."""
    rosters: list[dict] = []
    appearances: dict[str, list[dict]] = {}

    next_person_seq = 0

    def emit(persona: Persona, surface_name: str, variant_rule: str, shelter: dict) -> None:
        nonlocal next_person_seq
        next_person_seq += 1
        variants_list = sorted({v.surface_form for v in expand(surface_name)})
        roster_id = f"sr_{next_person_seq:04d}"
        rosters.append({
            "person_id": roster_id,
            "shelter_id": shelter["shelter_id"],
            "name": surface_name,
            "name_variants": variants_list,
            "age": persona.age,
            "language_spoken": persona.language_spoken,
            "arrival_time": random_arrival_time(rng),
            "school_or_employer": persona.school_or_employer,
            "distinguishing_features": persona.distinguishing_features,
            "contact_consent": rng.random() < 0.7,
            "shelter_location": jitter_geo(rng, float(shelter["lat"]), float(shelter["lon"])),
        })
        appearances.setdefault(persona.person_id, []).append({
            "doc_id": roster_id,
            "shelter_id": shelter["shelter_id"],
            "surface_name": surface_name,
            "variant_rule": variant_rule,
        })

    # STRESS: 2–3 shelter appearances, each a DIFFERENT variant
    for persona in STRESS_PERSONAS:
        all_variants: list[Variant] = expand(persona.canonical_name)
        # Always start with the canonical form in one shelter
        chosen_variants: list[tuple[str, str]] = [(persona.canonical_name, "canonical")]
        n_extras = rng.randint(1, 2)  # → 2–3 total shelter appearances
        # Pick distinct extra variants
        extra_pool = list(all_variants)
        rng.shuffle(extra_pool)
        for v in extra_pool[:n_extras]:
            chosen_variants.append((v.surface_form, v.rule))

        shelters_for_this = rng.sample(SHELTERS, k=len(chosen_variants))
        for (surface_name, rule), shelter in zip(chosen_variants, shelters_for_this):
            emit(persona, surface_name, rule, shelter)

    # FILLER: 1 shelter appearance, canonical only
    for persona in FILLER_PERSONAS:
        shelter = rng.choice(SHELTERS)
        emit(persona, persona.canonical_name, "canonical", shelter)

    return rosters, appearances


# ── missing-person reports (free-text descriptions, multilingual) ────────

def build_missing_person_reports(
    rng: random.Random,
    appearances: dict[str, list[dict]],
) -> list[dict]:
    """Reports from family seekers. Most match a real persona in the rosters
    (these will be gold-pair matches); ~10% are red herrings (no match in data)."""
    reports: list[dict] = []
    next_seq = 0

    def emit(*, subject_name: str, description: str, language: str,
             subject_age: int | None, source: str,
             location_text: str | None = None, location: dict | None = None) -> None:
        nonlocal next_seq
        next_seq += 1
        report = {
            "report_id": f"mpr_{next_seq:04d}",
            "subject_name": subject_name,
            "description": description,
            "language": language,
            "reported_at": random_arrival_time(rng),
            "source": source,
        }
        if subject_age is not None:
            report["subject_age"] = subject_age
        if location_text:
            report["last_known_location_text"] = location_text
        if location:
            report["last_known_location"] = location
        reports.append(report)

    # Each stress persona who has a description → one matching report
    for persona in STRESS_PERSONAS:
        if not persona.description:
            continue
        emit(
            subject_name=persona.canonical_name,
            description=persona.description,
            language=persona.description_language,
            subject_age=persona.age,
            source="family_member",
        )

    # Filler personas: half generate a generic report, half don't
    for persona in FILLER_PERSONAS:
        if rng.random() > 0.5:
            continue
        desc = (
            persona.description
            or f"Looking for {persona.canonical_name}, age {persona.age}. "
               f"{persona.distinguishing_features or 'No further details available.'}"
        )
        emit(
            subject_name=persona.canonical_name,
            description=desc,
            language=persona.description_language,
            subject_age=persona.age,
            source=rng.choice(["family_member", "friend", "coworker", "neighbour"]),
        )

    # Red herrings: 5 reports with names that don't match anyone in rosters
    red_herrings = [
        ("Joaquín Aguilar", 41, "es",
         "Busco a mi primo Joaquín Aguilar. Vive en Galveston pero estaba visitando Houston."),
        ("Stephanie Roberts", 26, "en",
         "Looking for my coworker Stephanie Roberts. She lived alone in Spring Branch."),
        ("Kenji Tanaka", 38, "en",
         "My neighbour Kenji Tanaka — I haven't seen him since the evacuation."),
        ("Ngozi Okeke", 33, "en",
         "Looking for Ngozi Okeke. She's a nurse at Park Plaza Hospital."),
        ("Beatriz Salinas", 59, "es",
         "Mi tía Beatriz Salinas vive en Pasadena. No tenemos noticias."),
    ]
    for name, age, lang, desc in red_herrings:
        emit(subject_name=name, description=desc, language=lang,
             subject_age=age, source="family_member")

    return reports


# ── reunification cases (open seeker queries) ────────────────────────────

def build_reunification_cases(
    rng: random.Random,
    appearances: dict[str, list[dict]],
) -> list[dict]:
    """Pre-seeded open cases: a seeker has searched, candidates may have been
    surfaced and verified / rejected / left pending."""
    cases: list[dict] = []
    next_seq = 0
    now = STORM_START + timedelta(hours=18)

    # 10 cases tied to stress personas (rich evidence, demo-grade)
    for i, persona in enumerate(STRESS_PERSONAS[:10]):
        status = rng.choice(["pending_verifier", "verified", "pending_verifier",
                             "no_match", "pending_verifier"])
        next_seq += 1
        case_appearances = appearances.get(persona.person_id, [])
        candidate_matches: list[dict] = []
        if case_appearances and status in ("pending_verifier", "verified"):
            # surface 1–2 candidates from the actual shelter appearances
            for app in case_appearances[: rng.randint(1, 2)]:
                candidate_matches.append({
                    "person_id": app["doc_id"],
                    "source_index": "shelter_rosters",
                    "confidence": round(rng.uniform(0.78, 0.97), 3),
                    "evidence": f"name match via {app['variant_rule']}, age match, school affiliation consistent",
                    "verifier_decision": "approved" if status == "verified" else "pending",
                    "verified_at": (now + timedelta(minutes=15 * i)).isoformat() if status == "verified" else None,
                })
        cases.append({
            "case_id": f"rc_{next_seq:04d}",
            "seeker_name": f"family_of_{persona.person_id}",
            "seeker_language": persona.description_language,
            "seeker_contact": f"+1-832-555-{1000 + i:04d}",
            "subject_name_as_given": persona.canonical_name,
            "subject_name_variants_explored": sorted({v.surface_form for v in expand(persona.canonical_name)}),
            "subject_age_estimate": persona.age,
            "last_known_location": jitter_geo(rng, 29.76, -95.37),
            "distinguishing_features": persona.distinguishing_features or "",
            "status": status,
            "candidate_matches": candidate_matches,
            "standing_query_active": status in ("no_match", "pending_verifier"),
            "created_at": (now - timedelta(hours=rng.randint(1, 12))).isoformat(),
            "resolved_at": (now + timedelta(hours=2)).isoformat() if status == "verified" else None,
        })

    # 20 standing-query cases tied to filler personas (no candidates surfaced yet)
    for i, persona in enumerate(FILLER_PERSONAS[:20]):
        next_seq += 1
        cases.append({
            "case_id": f"rc_{next_seq:04d}",
            "seeker_name": f"contact_{persona.person_id}",
            "seeker_language": persona.description_language,
            "seeker_contact": f"+1-713-555-{2000 + i:04d}",
            "subject_name_as_given": persona.canonical_name,
            "subject_name_variants_explored": [persona.canonical_name],
            "subject_age_estimate": persona.age,
            "last_known_location": jitter_geo(rng, 29.74, -95.45),
            "distinguishing_features": persona.distinguishing_features or "",
            "status": "no_match",
            "candidate_matches": [],
            "standing_query_active": True,
            "created_at": (now - timedelta(hours=rng.randint(2, 18))).isoformat(),
        })

    return cases


# ── social reports (multilingual, with Arabic stress subset) ─────────────

_SOCIAL_TEMPLATES_EN = [
    "Has anyone seen {name}? Last seen near {area}. Please share.",
    "If you've seen {name} ({age}), please contact me. Storm separated us.",
    "Looking for my {relation} {name}, missing since the hurricane.",
    "Update: still no word from {name}. {features}. Houston area.",
]
_SOCIAL_TEMPLATES_ES = [
    "¿Alguien ha visto a {name}? Última vez cerca de {area}. Por favor compartir.",
    "Si has visto a {name} ({age}), por favor contáctame. La tormenta nos separó.",
    "Busco a mi {relation} {name}, desaparecido desde el huracán.",
]
_SOCIAL_TEMPLATES_AR = [
    "هل رأى أحد {name}؟ آخر مرة شوهد بالقرب من {area}. يرجى المشاركة.",
    "أبحث عن قريبي {name}. مفقود منذ الإعصار.",
]
_AREAS = ["Memorial High", "Sharpstown", "Alief", "Bellaire", "George R. Brown", "NRG Center", "Westside"]
_RELATIONS_EN = ["sister", "brother", "cousin", "grandmother", "grandfather", "uncle", "aunt", "son", "daughter"]
_RELATIONS_ES = ["hermana", "hermano", "primo", "abuela", "tío", "tía", "hijo", "hija"]
_PLATFORMS = ["twitter", "facebook", "whatsapp_status", "reddit_r_houston"]


def build_social_reports(rng: random.Random) -> list[dict]:
    posts: list[dict] = []
    next_seq = 0
    now = STORM_START + timedelta(hours=6)

    def emit(text: str, language: str, mentioned: list[str]) -> None:
        nonlocal next_seq
        next_seq += 1
        posts.append({
            "report_id": f"soc_{next_seq:04d}",
            "text": text,
            "language": language,
            "mentioned_names": mentioned,
            "geo_location": jitter_geo(rng, 29.7 + rng.uniform(-0.05, 0.05), -95.4 + rng.uniform(-0.05, 0.05)),
            "source_platform": rng.choice(_PLATFORMS),
            "timestamp": (now + timedelta(minutes=rng.randint(0, 720))).isoformat(),
        })

    # For each stress persona, ~3 posts using different variants
    for persona in STRESS_PERSONAS:
        variants = [persona.canonical_name] + [v.surface_form for v in expand(persona.canonical_name)]
        n_posts = rng.randint(2, 4)
        for _ in range(n_posts):
            name = rng.choice(variants)
            if persona.description_language == "es":
                tpl = rng.choice(_SOCIAL_TEMPLATES_ES)
                text = tpl.format(name=name, age=persona.age, area=rng.choice(_AREAS),
                                  relation=rng.choice(_RELATIONS_ES))
                lang = "es"
            elif persona.description_language == "ar":
                tpl = rng.choice(_SOCIAL_TEMPLATES_AR)
                text = tpl.format(name=name, area=rng.choice(_AREAS))
                lang = "ar"
            else:
                tpl = rng.choice(_SOCIAL_TEMPLATES_EN)
                text = tpl.format(name=name, age=persona.age, area=rng.choice(_AREAS),
                                  relation=rng.choice(_RELATIONS_EN),
                                  features=persona.distinguishing_features or "")
                lang = "en"
            emit(text, lang, [name])

    # Noise: filler personas + generic non-name posts
    for persona in FILLER_PERSONAS[:25]:
        tpl = rng.choice(_SOCIAL_TEMPLATES_EN)
        text = tpl.format(name=persona.canonical_name, age=persona.age,
                          area=rng.choice(_AREAS), relation=rng.choice(_RELATIONS_EN),
                          features=persona.distinguishing_features or "")
        emit(text, "en", [persona.canonical_name])

    generic_noise = [
        ("Power's out across the Heights. Anyone got an update on the trunk lines?", "en"),
        ("Water rising fast on Bellaire. Stay safe everyone.", "en"),
        ("Sharpstown shelter is full, redirected to NRG Center. Tell people.", "en"),
        ("La carretera I-45 está cerrada. Eviten esa zona.", "es"),
        ("El refugio en Chavez High tiene espacio si alguien lo necesita.", "es"),
        ("الطريق مغلق بالقرب من شارب­ستاون. خذوا طريقًا آخر.", "ar"),
        ("Memorial Hospital is overcrowded, try Methodist West instead.", "en"),
    ]
    for text, lang in generic_noise:
        emit(text, lang, [])

    return posts


# ── gold pairs (the eval scoreboard input) ───────────────────────────────

def build_gold_pairs(
    appearances: dict[str, list[dict]],
    rosters: list[dict],
    reports: list[dict],
) -> list[dict]:
    """One JSONL line per eval case. Each case has a seeker query and the set
    of docs in our synthetic data that the agent SHOULD surface as matches."""
    pairs: list[dict] = []
    next_seq = 0

    def emit(query: str, language: str, persona: Persona | None,
             true_matches: list[dict], hard_negative: bool = False,
             notes: str = "") -> None:
        nonlocal next_seq
        next_seq += 1
        pairs.append({
            "case_id": f"gp_{next_seq:03d}",
            "seeker_query": query,
            "seeker_language": language,
            "expected_person_id": persona.person_id if persona else None,
            "expected_age": persona.age if persona else None,
            "true_matches": true_matches,
            "is_hard_negative": hard_negative,
            "notes": notes,
        })

    # 1) For each stress persona: query by canonical AND by 1-2 variants
    #    Every appearance (across shelters) is a valid match for any of those queries.
    for persona in STRESS_PERSONAS:
        apps = appearances.get(persona.person_id, [])
        if not apps:
            continue
        all_true = [
            {"doc_id": a["doc_id"], "found_in": "shelter_rosters",
             "doc_name": a["surface_name"], "shelter_id": a["shelter_id"],
             "match_rule": a["variant_rule"]}
            for a in apps
        ]

        # Query by canonical
        emit(persona.canonical_name, persona.description_language, persona,
             all_true, notes="canonical query")

        # Query by each variant that actually appears in a shelter (≠ canonical)
        non_canon_apps = [a for a in apps if a["variant_rule"] != "canonical"]
        for app in non_canon_apps[:2]:
            emit(app["surface_name"], persona.description_language, persona,
                 all_true, notes=f"query by {app['variant_rule']} variant")

    # 2) Filler personas: one query per persona, single match expected
    for persona in FILLER_PERSONAS[:20]:
        apps = appearances.get(persona.person_id, [])
        if not apps:
            continue
        emit(persona.canonical_name, persona.description_language, persona,
             [{"doc_id": apps[0]["doc_id"], "found_in": "shelter_rosters",
               "doc_name": apps[0]["surface_name"], "shelter_id": apps[0]["shelter_id"],
               "match_rule": "canonical"}],
             notes="filler — single canonical match")

    # 3) Hard negatives: queries that should return no shelter match
    hard_negatives = [
        ("Joaquín Aguilar", "es", "red herring: in reports but not in rosters"),
        ("Stephanie Roberts", "en", "red herring: in reports but not in rosters"),
        ("Kenji Tanaka", "en", "red herring: in reports but not in rosters"),
        ("Wei Zhang", "en", "not present anywhere"),
        ("Esperanza López", "es", "not present anywhere"),
        ("Yara Mansour", "ar", "not present anywhere"),
    ]
    for query, lang, note in hard_negatives:
        emit(query, lang, None, [], hard_negative=True, notes=note)

    return pairs


# ── orchestrator ─────────────────────────────────────────────────────────

def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DisasterLens synthetic data generation")
    print("=" * 60)

    rosters, appearances = build_shelter_rosters(rng)
    print(f"\n[1/5] shelter_rosters: {len(rosters)} docs from "
          f"{len(STRESS_PERSONAS)} stress + {len(FILLER_PERSONAS)} filler personas")
    write_ndjson(OUT_DIR / "shelter_rosters.ndjson", rosters)

    reports = build_missing_person_reports(rng, appearances)
    print(f"\n[2/5] missing_person_reports: {len(reports)} reports")
    cases = build_reunification_cases(rng, appearances)
    print(f"\n[3/5] reunification_cases: {len(cases)} cases")
    posts = build_social_reports(rng)
    print(f"\n[4/5] social_reports: {len(posts)} posts")

    # Embeddings: description for reports, text for social posts
    print(f"\n[5/5] computing embeddings client-side")
    client = build_client()
    desc_texts = [r["description"] for r in reports]
    desc_vectors = embed_many(client, desc_texts, label="missing_person_reports.description")
    for r, v in zip(reports, desc_vectors):
        r["description_embedding"] = v

    post_texts = [p["text"] for p in posts]
    post_vectors = embed_many(client, post_texts, label="social_reports.text")
    for p, v in zip(posts, post_vectors):
        p["text_embedding"] = v

    write_ndjson(OUT_DIR / "missing_person_reports.ndjson", reports)
    write_ndjson(OUT_DIR / "reunification_cases.ndjson", cases)
    write_ndjson(OUT_DIR / "social_reports.ndjson", posts)

    # Gold pairs
    gold = build_gold_pairs(appearances, rosters, reports)
    write_ndjson(EVALS_DIR / "family_pairs.jsonl", gold)
    print(f"\n[gold] {len(gold)} eval cases "
          f"({sum(1 for g in gold if g['is_hard_negative'])} hard negatives)")

    print("\n✓ done.")


if __name__ == "__main__":
    main()
