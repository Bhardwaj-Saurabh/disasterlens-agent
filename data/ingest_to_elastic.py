"""Bulk-ingest the synthetic NDJSON into Elastic.

Reads each data/synthetic/<index>.ndjson and bulk-indexes it into <index>. All
embeddings are already baked into the docs by generate_synthetic.py — the
ingest path here is a plain `_bulk` with no pipeline.

`--reset` wipes each index before re-ingesting (use after data regeneration).

Run:
    uv run python -m data.ingest_to_elastic           # additive
    uv run python -m data.ingest_to_elastic --reset   # wipe + reload
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

load_dotenv(".env.local")

SYNTHETIC_DIR = Path(__file__).resolve().parent / "synthetic"

INDEX_FILES = {
    "shelter_rosters":        SYNTHETIC_DIR / "shelter_rosters.ndjson",
    "missing_person_reports": SYNTHETIC_DIR / "missing_person_reports.ndjson",
    "reunification_cases":    SYNTHETIC_DIR / "reunification_cases.ndjson",
    "social_reports":         SYNTHETIC_DIR / "social_reports.ndjson",
}


def build_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=60,
    )


def read_ndjson(path: Path) -> list[dict]:
    docs: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs


def id_key_for(index: str) -> str | None:
    """Pick which doc field doubles as the ES _id, so re-ingest is idempotent."""
    return {
        "shelter_rosters":        "person_id",
        "missing_person_reports": "report_id",
        "reunification_cases":    "case_id",
        "social_reports":         "report_id",
    }.get(index)


def ingest(client: Elasticsearch, index: str, docs: list[dict]) -> None:
    id_key = id_key_for(index)
    actions = [
        {"_op_type": "index", "_index": index,
         "_id": doc.get(id_key) if id_key else None,
         "_source": doc}
        for doc in docs
    ]
    success, errors = bulk(client, actions, refresh="wait_for", raise_on_error=False)
    if errors:
        print(f"  ✗ {len(errors)} errors during {index} bulk ingest")
        for err in errors[:3]:
            print(f"      {err}")
        if len(errors) > 3:
            print(f"      ... {len(errors) - 3} more")
        sys.exit(1)
    print(f"  ✓ {index}: {success} docs indexed")


def reset_index(client: Elasticsearch, index: str) -> None:
    print(f"  → wiping {index}")
    client.delete_by_query(index=index, query={"match_all": {}}, refresh=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="Delete all docs in each index before re-ingesting")
    args = parser.parse_args()

    client = build_client()
    if not client.ping():
        sys.exit("✗ Elasticsearch ping failed")
    print(f"✓ connected to {os.environ['ELASTIC_ENDPOINT']}")

    for index, path in INDEX_FILES.items():
        if not path.exists():
            sys.exit(f"✗ missing {path} — run `uv run python -m data.generate_synthetic` first")
        docs = read_ndjson(path)
        print(f"\n{index} ({len(docs)} docs from {path.name})")
        if args.reset:
            reset_index(client, index)
        ingest(client, index, docs)

    print("\n✓ done. Counts on cluster:")
    for index in INDEX_FILES:
        count = client.count(index=index)["count"]
        print(f"  • {index} ({count} docs)")


if __name__ == "__main__":
    main()
