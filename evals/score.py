"""Eval scoreboard — scores the retrieval layer against the gold set.

Reads evals/family_pairs.jsonl. For each case, expands the seeker query through
data.variants.expand(), runs a multi-strategy multi_match against shelter_rosters,
and scores top-K results against the labelled true matches.

Outputs:
  • Overall recall@K, MRR, per-case latency
  • Hard-negative precision (cases that should return zero high-score matches)
  • Per-rule breakdown — the "recall on transliterated/nickname subset" required
    by PRD §13 lives in the `nickname`, `arabic_romanise`, `fold_diacritics`,
    `name_order_swap`, `vietnamese_fold` rows
  • Optional CSV at evals/score_results.csv with one row per case

Run:
    uv run python -m evals.score                       # default K=5
    uv run python -m evals.score --top-k 3 --csv       # change K, write CSV
    uv run python -m evals.score --hard-negative-threshold 6.0
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from data.variants import expand, fold_diacritics

load_dotenv(".env.local")

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_FILE = REPO_ROOT / "evals" / "family_pairs.jsonl"
RESULTS_CSV = REPO_ROOT / "evals" / "score_results.csv"

INDEX = "shelter_rosters"
# A non-hard-negative result whose top-1 ES score is below this is considered
# "no high-confidence match" — used to compute hard-negative precision.
DEFAULT_HARD_NEG_THRESHOLD = 6.0

# Rules considered "hero" for the PRD §13 "recall on transliterated/nickname subset"
HERO_RULES = {"nickname", "arabic_romanise", "fold_diacritics",
              "name_order_swap", "vietnamese_fold", "initial_form"}

# Fused-confidence threshold — matches agent/config.LOW_CONFIDENCE_FLOOR.
# If fused(top1) ≥ this, the agent would surface a candidate; below, it would not.
FUSED_CONFIDENCE_THRESHOLD = 0.75


def _tokens(name: str) -> set[str]:
    """Tokenise a name: lowercase + asciifold + strip trailing punctuation."""
    return {
        tok.strip(".,'\"")
        for tok in fold_diacritics(name).lower().split()
        if tok.strip(".,'\"")
    }


def query_token_set(name: str) -> set[str]:
    """All plausible tokens for a seeker query — original + every variant
    expansion — flattened. The agent uses this implicitly via name_variants."""
    forms = [name] + [v.surface_form for v in expand(name)]
    out: set[str] = set()
    for f in forms:
        out |= _tokens(f)
    return out


def fused_confidence(
    *,
    top1_score: float,
    top1_name: str,
    seeker_query: str,
    expected_age: int | None = None,
    candidate_age: int | None = None,
    score_ceiling: float = 12.0,
) -> tuple[float, dict]:
    """Combine retrieval score + token-overlap + age into one number in [0, 1].

    The token-overlap term is the difference-maker: pure BM25 gives "Esperanza
    López" → "Esperanza Vargas" a high score (first-name match), but the
    candidate's token "vargas" doesn't appear in the query's variant-expanded
    token set, so overlap = 0.5 and the fused score drops below threshold.

    Returns (confidence, breakdown) where breakdown is logged for the CSV.
    """
    q_tokens = query_token_set(seeker_query)
    c_tokens = _tokens(top1_name)
    if not c_tokens:
        return 0.0, {"name_norm": 0, "overlap": 0, "age_score": 0}
    overlap = len(q_tokens & c_tokens) / len(c_tokens)
    name_norm = min(top1_score / score_ceiling, 1.0)
    name_score = name_norm * overlap

    if expected_age is not None and candidate_age is not None:
        age_score = 1.0 if abs(int(expected_age) - int(candidate_age)) <= 3 else 0.4
    else:
        age_score = 0.7  # neutral when unknown

    confidence = name_score * 0.7 + age_score * 0.3
    return confidence, {
        "name_norm": round(name_norm, 3),
        "overlap": round(overlap, 3),
        "age_score": round(age_score, 3),
    }


def build_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=30,
    )


def load_cases() -> list[dict]:
    if not GOLD_FILE.exists():
        sys.exit(f"✗ missing {GOLD_FILE} — run `uv run python -m data.generate_synthetic` first")
    cases: list[dict] = []
    with GOLD_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def query_for(case: dict) -> dict:
    """Build the multi-strategy ES query for a case using the same name_variants
    expansion the agent uses at runtime.

    Each variant is its own `multi_match` clause inside a `bool.should` — BM25
    picks the best clause without inflating scores via token repetition (which
    happens if you concatenate variants into one query string).
    """
    name = case["seeker_query"]
    variants = expand(name)
    surface_forms = list(dict.fromkeys([name] + [v.surface_form for v in variants]))
    return {
        "size": 10,
        "query": {
            # dis_max: best-variant-wins. bool.should would sum the scores of
            # every matching variant, double-counting the same doc and inflating
            # scores when several variants overlap (e.g. "Esperanza" vs "Esperanza
            # Lopez" both match a roster entry named "Esperanza Vargas").
            "dis_max": {
                "tie_breaker": 0.1,  # small bonus for matching multiple variants
                "queries": [
                    {
                        "multi_match": {
                            "query": form,
                            "fields": ["name^3", "name.phonetic", "name.translit"],
                            "type": "best_fields",
                        }
                    }
                    for form in surface_forms
                ],
            }
        },
        "_source": ["name", "shelter_id", "age", "language_spoken"],
    }


def score_case(client: Elasticsearch, case: dict, top_k: int, hard_neg_threshold: float) -> dict:
    body = query_for(case)
    t0 = time.time()
    resp = client.search(index=INDEX, body=body)
    elapsed_ms = (time.time() - t0) * 1000

    hits = resp["hits"]["hits"][:top_k]
    top1 = hits[0] if hits else None
    top1_score = top1["_score"] if top1 else 0.0
    top1_name = top1["_source"].get("name", "") if top1 else ""
    top1_age = top1["_source"].get("age") if top1 else None

    expected_ids = {tm["doc_id"] for tm in case["true_matches"]}
    expected_rules = {tm["match_rule"] for tm in case["true_matches"]}

    retrieved_ids = [h["_id"] for h in hits]
    true_positives = [h for h in hits if h["_id"] in expected_ids]
    found_ids = {h["_id"] for h in true_positives}

    recall = len(found_ids) / len(expected_ids) if expected_ids else None
    first_hit_rank = next(
        (i + 1 for i, h in enumerate(hits) if h["_id"] in expected_ids),
        None,
    )
    reciprocal_rank = (1.0 / first_hit_rank) if first_hit_rank else 0.0
    precision = len(true_positives) / len(hits) if hits else 0.0

    hard_neg_ok = None
    if case["is_hard_negative"]:
        hard_neg_ok = top1_score < hard_neg_threshold

    # Fused confidence — what the agent would compute over the top-1 hit
    fused, breakdown = fused_confidence(
        top1_score=top1_score,
        top1_name=top1_name,
        seeker_query=case["seeker_query"],
        expected_age=case.get("expected_age"),
        candidate_age=top1_age,
    )
    fired = fused >= FUSED_CONFIDENCE_THRESHOLD
    top1_in_truth = top1 is not None and top1["_id"] in expected_ids
    # TP: positive case, fired, top-1 is truth.  TN: hard-neg, did not fire.
    # FP: fired with wrong top-1 (positive miss) OR hard-neg.  FN: positive, did not fire.
    if case["is_hard_negative"]:
        outcome = "TN" if not fired else "FP"
    else:
        if not fired:
            outcome = "FN"
        elif top1_in_truth:
            outcome = "TP"
        else:
            outcome = "FP"

    return {
        "case_id": case["case_id"],
        "query": case["seeker_query"],
        "language": case["seeker_language"],
        "is_hard_negative": case["is_hard_negative"],
        "expected_count": len(expected_ids),
        "expected_rules": sorted(expected_rules),
        "retrieved_ids": retrieved_ids[:top_k],
        "true_positive_ids": [h["_id"] for h in true_positives],
        "recall_at_k": recall,
        "precision_at_k": precision,
        "first_hit_rank": first_hit_rank,
        "reciprocal_rank": reciprocal_rank,
        "top1_score": round(top1_score, 3),
        "top1_name": top1_name,
        "hard_negative_ok": hard_neg_ok,
        "fused_confidence": round(fused, 3),
        "fused_breakdown": breakdown,
        "fused_fired": fired,
        "fused_outcome": outcome,
        "latency_ms": round(elapsed_ms, 1),
    }


def aggregate(results: list[dict]) -> dict:
    positive = [r for r in results if not r["is_hard_negative"]]
    hard_negs = [r for r in results if r["is_hard_negative"]]

    recalls = [r["recall_at_k"] for r in positive if r["recall_at_k"] is not None]
    precisions = [r["precision_at_k"] for r in positive]
    mrrs = [r["reciprocal_rank"] for r in positive]
    latencies = [r["latency_ms"] for r in results]
    languages = {r["language"] for r in positive if r["recall_at_k"] and r["recall_at_k"] > 0}

    hard_neg_correct = [r for r in hard_negs if r["hard_negative_ok"]]

    # Per-rule recall: for cases where rule R is among expected_rules, was the recall > 0?
    per_rule_total: dict[str, int] = defaultdict(int)
    per_rule_hit: dict[str, int] = defaultdict(int)
    for r in positive:
        for rule in r["expected_rules"]:
            per_rule_total[rule] += 1
            if r["recall_at_k"] and r["recall_at_k"] > 0:
                per_rule_hit[rule] += 1
    per_rule = {
        rule: {"n": per_rule_total[rule], "recall>0": per_rule_hit[rule] / per_rule_total[rule]}
        for rule in sorted(per_rule_total)
    }

    hero_total = sum(per_rule_total[r] for r in HERO_RULES if r in per_rule_total)
    hero_hit = sum(per_rule_hit[r] for r in HERO_RULES if r in per_rule_total)
    hero_recall = hero_hit / hero_total if hero_total else None

    # Fused-mode metrics — outcome distribution and derived precision/recall.
    counts = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
    for r in results:
        counts[r["fused_outcome"]] += 1
    fused_precision = (counts["TP"] / (counts["TP"] + counts["FP"])
                       if (counts["TP"] + counts["FP"]) else None)
    fused_recall = (counts["TP"] / (counts["TP"] + counts["FN"])
                    if (counts["TP"] + counts["FN"]) else None)
    fused_f1 = ((2 * fused_precision * fused_recall) / (fused_precision + fused_recall)
                if fused_precision and fused_recall else None)
    fused_hard_neg_rejection = (counts["TN"] / (counts["TN"] + sum(
        1 for r in hard_negs if r["fused_outcome"] == "FP"
    )) if hard_negs else None)

    return {
        "n_positive_cases": len(positive),
        "n_hard_negative_cases": len(hard_negs),
        "mean_recall_at_k": statistics.mean(recalls) if recalls else 0.0,
        "mean_precision_at_k": statistics.mean(precisions) if precisions else 0.0,
        "mrr": statistics.mean(mrrs) if mrrs else 0.0,
        "languages_with_hit": sorted(languages),
        "hard_negative_precision": (len(hard_neg_correct) / len(hard_negs)) if hard_negs else None,
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_ms": (statistics.quantiles(latencies, n=20)[-1]
                          if len(latencies) >= 20 else max(latencies, default=0.0)),
        "hero_subset_recall": hero_recall,
        "hero_subset_n": hero_total,
        "per_rule": per_rule,
        # Fused-confidence-mode aggregates
        "fused_outcome_counts": counts,
        "fused_precision": fused_precision,
        "fused_recall": fused_recall,
        "fused_f1": fused_f1,
        "fused_hard_neg_rejection": fused_hard_neg_rejection,
    }


def print_report(agg: dict, top_k: int, hard_neg_threshold: float) -> None:
    print()
    print("=" * 64)
    print(f"  DisasterLens eval — retrieval (recall@{top_k}) + fused (precision@conf)")
    print("=" * 64)
    print(f"  positive cases:           {agg['n_positive_cases']}")
    print(f"  hard-negative cases:      {agg['n_hard_negative_cases']}")
    print()
    print("  ─── retrieval layer ────────────────────────────────────")
    print(f"  mean recall@{top_k}:           {agg['mean_recall_at_k']:.3f}")
    print(f"  mean precision@{top_k}:        {agg['mean_precision_at_k']:.3f}")
    print(f"  MRR:                      {agg['mrr']:.3f}")
    print(f"  hero-subset recall:       "
          f"{agg['hero_subset_recall']:.3f}  (n={agg['hero_subset_n']})")
    print(f"  languages with ≥1 hit:    "
          f"{', '.join(agg['languages_with_hit'])}  (n={len(agg['languages_with_hit'])})")
    if agg["hard_negative_precision"] is not None:
        print(f"  hard-neg precision:       "
              f"{agg['hard_negative_precision']:.3f}  (top1 score < {hard_neg_threshold})")
    print(f"  median / p95 latency:     {agg['median_latency_ms']:.1f} / {agg['p95_latency_ms']:.1f} ms")
    print()
    print(f"  ─── fused-confidence layer (threshold ≥ {FUSED_CONFIDENCE_THRESHOLD}) ──────")
    counts = agg["fused_outcome_counts"]
    print(f"  outcome counts:           "
          f"TP={counts['TP']}  FP={counts['FP']}  FN={counts['FN']}  TN={counts['TN']}")
    if agg["fused_precision"] is not None:
        print(f"  fused precision:          {agg['fused_precision']:.3f}"
              f"  ◄ headline number: PRD §16 target ≥ 0.90")
    if agg["fused_recall"] is not None:
        print(f"  fused recall:             {agg['fused_recall']:.3f}")
    if agg["fused_f1"] is not None:
        print(f"  fused F1:                 {agg['fused_f1']:.3f}")
    if agg["fused_hard_neg_rejection"] is not None:
        print(f"  hard-neg rejection rate:  {agg['fused_hard_neg_rejection']:.3f}"
              "  (TN / (TN + hard-neg FP))")
    print()
    print(f"  Per-rule recall (case-level: did ≥1 expected match land in top-{top_k}?)")
    for rule, m in agg["per_rule"].items():
        bar = "█" * int(m["recall>0"] * 20)
        print(f"    {rule:18}  {m['recall>0']:.3f}  n={m['n']:3d}  {bar}")
    print()


def write_csv(results: list[dict]) -> None:
    fields = [
        "case_id", "query", "language", "is_hard_negative",
        "expected_count", "recall_at_k", "precision_at_k",
        "first_hit_rank", "reciprocal_rank",
        "top1_name", "top1_score",
        "fused_confidence", "fused_fired", "fused_outcome",
        "latency_ms",
    ]
    with RESULTS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = {k: r[k] for k in fields}
            w.writerow(row)
    print(f"  → wrote {RESULTS_CSV.relative_to(Path.cwd())}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--hard-negative-threshold", type=float, default=DEFAULT_HARD_NEG_THRESHOLD)
    parser.add_argument("--csv", action="store_true", help="Write per-case results to CSV")
    parser.add_argument("--show-failures", action="store_true",
                        help="Print every case with recall < 1.0")
    args = parser.parse_args()

    client = build_client()
    cases = load_cases()
    print(f"Loaded {len(cases)} eval cases from {GOLD_FILE.name}")

    results = [score_case(client, c, args.top_k, args.hard_negative_threshold) for c in cases]

    if args.show_failures:
        print("\nFused-mode failures (FP / FN cases the agent layer would get wrong):")
        for r in results:
            if r["fused_outcome"] in {"FP", "FN"}:
                tag = "HN→FP" if r["is_hard_negative"] else r["fused_outcome"]
                print(f"  ✗ {tag:5} {r['case_id']}  {r['query']!r}")
                print(f"          top1={r['top1_name']!r}  score={r['top1_score']}  "
                      f"conf={r['fused_confidence']:.3f}  brk={r['fused_breakdown']}")

    agg = aggregate(results)
    print_report(agg, args.top_k, args.hard_negative_threshold)

    if args.csv:
        write_csv(results)


if __name__ == "__main__":
    main()
