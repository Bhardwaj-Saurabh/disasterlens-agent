"""Client-side text embedding via the disasterlens_e5 inference endpoint.

Used by generate_synthetic.py to bake 384-d vectors into docs before bulk
ingestion. Calls POST _inference/text_embedding/disasterlens_e5 directly —
the ingest-pipeline auto-embed path is broken on Elastic Cloud Serverless 9.5
(silently drops the embedding; see memory:project-inference-pipeline-silent-drop).

The endpoint is configured with adaptive_allocations[min=0], so the first call
after idle takes ~10-30s while the model is warmed up. Subsequent calls are fast.
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError

load_dotenv(".env.local")

INFERENCE_ID = "disasterlens_e5"
EMBED_DIM = 384


def build_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=60,
    )


def embed_one(client: Elasticsearch, text: str) -> list[float]:
    """Embed a single string. Retries once on 408 (cold-start)."""
    for attempt in (1, 2):
        try:
            resp = client.inference.inference(inference_id=INFERENCE_ID, input=text)
            return list(resp["text_embedding"][0]["embedding"])
        except ApiError as exc:
            if exc.status_code == 408 and attempt == 1:
                print(f"  ↻ inference cold (408), retrying after 15s warm-up")
                time.sleep(15)
                continue
            raise
    raise RuntimeError("unreachable")


def embed_many(client: Elasticsearch, texts: list[str], label: str = "texts") -> list[list[float]]:
    """Embed a batch of strings. The endpoint accepts a list input directly,
    so this is a single round-trip — much faster than per-string calls."""
    if not texts:
        return []
    print(f"  → embedding {len(texts)} {label} via {INFERENCE_ID} …", flush=True)
    t0 = time.time()
    for attempt in (1, 2):
        try:
            resp = client.inference.inference(inference_id=INFERENCE_ID, input=texts)
            vectors = [list(item["embedding"]) for item in resp["text_embedding"]]
            print(f"    ✓ done in {time.time() - t0:.1f}s  ({len(vectors)} vectors, dim={len(vectors[0])})")
            return vectors
        except ApiError as exc:
            if exc.status_code == 408 and attempt == 1:
                print(f"    ↻ cold (408), retrying after 15s")
                time.sleep(15)
                continue
            raise
    raise RuntimeError("unreachable")
