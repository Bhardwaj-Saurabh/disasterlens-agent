"""Set up the Elastic inference endpoint for E5-multilingual embeddings.

Creates a `disasterlens_e5` text_embedding endpoint backed by
`.multilingual-e5-small` (384-d, preloaded on Elastic Cloud Serverless).
Idempotent: skips if the endpoint already exists.

**Why no ingest pipeline:** an initial attempt wired this endpoint into a
`disasterlens_embed` ingest pipeline with `default_pipeline` set on the
embedding indices. On Elastic Cloud Serverless 9.5 the `inference` processor
silently dropped the embedding output (leaking `model_id` to `_source` but
not writing the dense_vector). `_simulate` reproduced the embedding fine
but the production write path did not — see commit history. The data
generator now calls this endpoint directly (POST _inference/text_embedding/...)
and writes the vector into the doc before bulk-indexing. Same model, same
vectors, simpler debug story.

Run with:
    uv run python -m scripts.setup_inference
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError, NotFoundError

load_dotenv(".env.local")

INFERENCE_ID = "disasterlens_e5"
MODEL_ID = ".multilingual-e5-small"


def build_client() -> Elasticsearch:
    return Elasticsearch(
        hosts=[os.environ["ELASTIC_ENDPOINT"]],
        api_key=os.environ["ELASTIC_API_KEY"],
        request_timeout=60,
    )


def put_inference_endpoint(client: Elasticsearch) -> None:
    try:
        existing = client.inference.get(inference_id=INFERENCE_ID)
        if existing.get("endpoints"):
            print(f"  ↻ _inference/text_embedding/{INFERENCE_ID} already exists — leaving as-is")
            return
    except NotFoundError:
        pass

    print(f"→ PUT _inference/text_embedding/{INFERENCE_ID}  (model={MODEL_ID})")
    try:
        client.inference.put(
            task_type="text_embedding",
            inference_id=INFERENCE_ID,
            inference_config={
                "service": "elasticsearch",
                "service_settings": {
                    "model_id": MODEL_ID,
                    "adaptive_allocations": {
                        "enabled": True,
                        "min_number_of_allocations": 0,
                        "max_number_of_allocations": 1,
                    },
                    "num_threads": 1,
                },
            },
        )
        print("  ✓ inference endpoint created")
    except ApiError as exc:
        if exc.status_code == 408:
            print("  ↻ created but still deploying (408) — will warm up on first inference")
        else:
            raise


def main() -> None:
    client = build_client()
    if not client.ping():
        sys.exit("✗ Elasticsearch ping failed")
    print(f"✓ connected to {os.environ['ELASTIC_ENDPOINT']}")
    put_inference_endpoint(client)
    print(f"\n✓ inference endpoint ready. Call it from the data generator with:")
    print(f"    POST _inference/text_embedding/{INFERENCE_ID}  body={{\"input\": \"...\"}}")


if __name__ == "__main__":
    main()
