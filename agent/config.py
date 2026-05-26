"""Sprint 1 Day 1 stub — just enough config for the hello-world.
Real safety settings, thresholds, and prompts arrive in Sprint 2.
"""
import os

from dotenv import load_dotenv

load_dotenv(".env.local")

GCP_PROJECT_ID = os.environ["GCP_PROJECT_ID"]
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")

ELASTIC_ENDPOINT = os.environ["ELASTIC_ENDPOINT"]
ELASTIC_API_KEY = os.environ["ELASTIC_API_KEY"]
# Kibana endpoint — Agent Builder MCP (/api/agent_builder/*) lives on Kibana, not Elasticsearch.
# On Elastic Cloud Serverless, swap `.es.` for `.kb.` in the cluster hostname.
KIBANA_ENDPOINT = os.environ.get(
    "KIBANA_ENDPOINT",
    ELASTIC_ENDPOINT.replace(".es.", ".kb."),
)
