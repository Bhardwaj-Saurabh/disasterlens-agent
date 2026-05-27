"""evals.explain_match — render the analyzer stack firing on a single match.

The README's strongest technical claim is "compounded name matching across
five strategies." This CLI proves it in 5 seconds of screen time: it runs the
hero query against `shelter_rosters` with `explain=true` and prints the BM25
contribution from each analyzer (`name`, `name.phonetic`, `name.translit`),
the variants the agent would expand the query into, and the top hit's score
breakdown.

Run:
    uv run python -m evals.explain_match --query "محمد خان"
    uv run python -m evals.explain_match --query "Mohammed Khan"
    uv run python -m evals.explain_match --hero          # default: محمد خان

The intended frame for the demo: pause the video on this output so the
analyzer column on each match line is visible. The viewer sees three
analyzers all contributing to the same composite score — the thing that
ARC Safe and Well, Google Person Finder, and NamUs cannot do.
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from data.variants import expand

load_dotenv(".env.local")

INDEX = "shelter_rosters"
HERO_QUERY = "محمد خان"  # Arabic-script "Mohammed Khan" — the demo unscripted moment

_ANALYZER_FIELDS = ("name", "name.phonetic", "name.translit")


def _client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=30,
    )


def _build_query(name: str) -> dict:
    """The same multi-strategy dis_max the agent uses at runtime + via evals.score."""
    forms = list(dict.fromkeys([name] + [v.surface_form for v in expand(name)]))
    return {
        "size": 3,
        "explain": True,
        "query": {
            "dis_max": {
                "tie_breaker": 0.1,
                "queries": [
                    {
                        "multi_match": {
                            "query": form,
                            "fields": ["name^3", "name.phonetic", "name.translit"],
                            "type": "best_fields",
                        }
                    }
                    for form in forms
                ],
            }
        },
        "_source": ["name", "shelter_id", "age", "language_spoken"],
    }


def _walk_analyzer_contributions(explanation: dict) -> dict[str, float]:
    """Walk the recursive `_explanation` tree and sum scores by indexed field
    (`name`, `name.phonetic`, `name.translit`). The leaves of an ES explanation
    carry a `description` string that names the field via patterns like
    `weight(name.phonetic:mhmt in 0)` — we parse the field token out and bucket."""
    totals: dict[str, float] = {}

    def visit(node: dict) -> None:
        desc = (node.get("description") or "")
        # `weight(<field>:<term> ...)` is the canonical BM25 leaf; we also see
        # `weight(FunctionScoreQuery(<field>:...))` etc. — extract the first
        # `<field>:` token whose prefix matches one of our analyzer fields.
        if desc.startswith("weight("):
            inside = desc[len("weight("):]
            for f in _ANALYZER_FIELDS:
                if inside.startswith(f + ":") or (":" + f + ":") in inside:
                    totals[f] = totals.get(f, 0.0) + float(node.get("value") or 0.0)
                    break
        for child in (node.get("details") or []):
            visit(child)

    visit(explanation)
    return totals


def _bar(value: float, max_value: float, width: int = 24) -> str:
    if max_value <= 0:
        return ""
    n = int(round(value / max_value * width))
    return "█" * n + "·" * (width - n)


def _print_variants(name: str) -> None:
    variants = expand(name)
    print(f"\nVariant expansion (data.variants.expand → {len(variants)} forms):")
    if not variants:
        print("  (none — name had no diacritics, nicknames, or script convertible by ICU)")
        return
    by_rule: dict[str, list[str]] = {}
    for v in variants:
        by_rule.setdefault(v.rule, []).append(v.surface_form)
    for rule, forms in by_rule.items():
        joined = ", ".join(forms[:6]) + (" …" if len(forms) > 6 else "")
        print(f"  [{rule:18}] {joined}")


def _print_hit(rank: int, hit: dict) -> None:
    src = hit.get("_source", {}) or {}
    contributions = _walk_analyzer_contributions(hit.get("_explanation") or {})
    total = float(hit.get("_score") or 0.0)
    print(f"\n  #{rank}  {src.get('name')!r}  ({hit.get('_id')}, shelter={src.get('shelter_id')}, age={src.get('age')})")
    print(f"       composite _score = {total:.3f}")
    if not contributions:
        print("       (analyzer breakdown unavailable — explanation tree had no recognised leaves)")
        return
    max_v = max(contributions.values())
    print(f"       {'analyzer':22} {'score':>7}   contribution")
    for field in _ANALYZER_FIELDS:
        v = contributions.get(field, 0.0)
        print(f"       {field:22} {v:7.3f}   {_bar(v, max_v)}")


def explain(query: str) -> int:
    es = _client()
    print("=" * 72)
    print(f"  DisasterLens — analyzer-stack explanation")
    print("=" * 72)
    print(f"\nQuery: {query!r}")
    _print_variants(query)

    body = _build_query(query)
    resp = es.search(index=INDEX, body=body)
    hits = resp.get("hits", {}).get("hits", [])
    if not hits:
        print("\n(no hits — was data ingested? `uv run python -m data.ingest_to_elastic --reset`)")
        return 1
    print(f"\nTop {len(hits)} hits — composite score = best-clause from `dis_max`:")
    for i, hit in enumerate(hits, start=1):
        _print_hit(i, hit)

    print(textwrap.dedent("""
        ─────────────────────────────────────────────────────────────────────
        Reading the breakdown:
          • `name`          — standard analyzer + nickname synonym_graph
                              (Mohammed ↔ Muhammad, Carlos ↔ Carlitos)
          • `name.phonetic` — double-metaphone codes (MHMT for محمد romanisations)
          • `name.translit` — ICU folding + nickname graph; handles diacritics
                              and script conversion (محمد → mhmd)
        The dis_max query picks the best-scoring clause across all expanded
        variants and analyzer fields. Three analyzers contributing to one
        composite score is what ARC Safe and Well / Google Person Finder /
        NamUs cannot do natively.
        ─────────────────────────────────────────────────────────────────────
    """).strip())
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--query", help="Seeker query (preserve script + diacritics)")
    parser.add_argument("--hero", action="store_true",
                        help=f"Use the hero query {HERO_QUERY!r}")
    args = parser.parse_args()
    if args.hero or not args.query:
        query = HERO_QUERY
    else:
        query = args.query
    sys.exit(explain(query))


if __name__ == "__main__":
    main()
