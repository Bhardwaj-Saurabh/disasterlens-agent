"""Register the DisasterLens synonyms set and 4 Elasticsearch indices.

Idempotent: re-running converges to the same state (synonyms set overwritten,
existing indices left alone with a notice).

Run with:
    uv run python -m scripts.create_indices
    uv run python -m scripts.create_indices --recreate   # delete + recreate indices
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import BadRequestError, NotFoundError

load_dotenv(".env.local")

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPINGS_DIR = REPO_ROOT / "data" / "mappings"
NICKNAMES_FILE = REPO_ROOT / "data" / "analysis" / "nicknames.txt"

SYNONYMS_SET_ID = "disasterlens_nicknames"
INDEX_NAMES = (
    "shelter_rosters",
    "missing_person_reports",
    "reunification_cases",
    "social_reports",
)


def parse_synonyms(path: Path) -> list[dict[str, str]]:
    """Parse a Solr-style synonyms file into the ES Synonyms API body format."""
    rules: list[dict[str, str]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=>" in line:
            sys.exit(f"{path}:{line_no} directional rules not yet supported")
        rules.append({"id": f"rule_{line_no}", "synonyms": line})
    return rules


def build_client() -> Elasticsearch:
    endpoint = os.environ["ELASTIC_ENDPOINT"]
    api_key = os.environ["ELASTIC_API_KEY"]
    return Elasticsearch(hosts=[endpoint], api_key=api_key, request_timeout=30)


def put_synonyms_set(client: Elasticsearch, rules: list[dict[str, str]]) -> None:
    print(f"→ PUT _synonyms/{SYNONYMS_SET_ID} ({len(rules)} rules)")
    client.synonyms.put_synonym(id=SYNONYMS_SET_ID, synonyms_set=rules)
    print(f"  ✓ synonyms set written")


def create_index(client: Elasticsearch, name: str, recreate: bool) -> None:
    mapping = json.loads((MAPPINGS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    exists = client.indices.exists(index=name)
    if exists and recreate:
        print(f"→ DELETE {name}")
        client.indices.delete(index=name)
        exists = False
    if exists:
        print(f"  ↻ {name} already exists — skipping (use --recreate to overwrite)")
        return
    print(f"→ PUT {name}")
    client.indices.create(index=name, **mapping)
    print(f"  ✓ {name} created")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true",
                        help="Delete existing indices before recreating (destroys data)")
    args = parser.parse_args()

    client = build_client()
    if not client.ping():
        sys.exit("✗ Elasticsearch ping failed — check ELASTIC_ENDPOINT and ELASTIC_API_KEY")
    print(f"✓ connected to {os.environ['ELASTIC_ENDPOINT']}")

    rules = parse_synonyms(NICKNAMES_FILE)
    put_synonyms_set(client, rules)

    for name in INDEX_NAMES:
        create_index(client, name, args.recreate)

    print("\n✓ done. Indices on cluster:")
    for name in INDEX_NAMES:
        if client.indices.exists(index=name):
            count = client.count(index=name)["count"]
            print(f"  • {name} ({count} docs)")


if __name__ == "__main__":
    try:
        main()
    except (BadRequestError, NotFoundError) as exc:
        sys.exit(f"✗ Elasticsearch error: {exc}")
