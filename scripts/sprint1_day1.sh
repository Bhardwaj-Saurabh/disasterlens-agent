#!/usr/bin/env bash
# DisasterLens — Sprint 1 Day 1 setup.
#
# Purpose: de-risk the two biggest unknowns before any product code:
#   1. Can ADK's MCPToolset talk to Elastic's Agent Builder MCP?
#   2. Can we register custom Agent Builder skills on the Serverless trial?
#
# This script is idempotent. Re-running it should converge to the same state.
#
# Usage:
#   ./scripts/sprint1_day1.sh preflight     # check local tools (gcloud, uv, jq)
#   ./scripts/sprint1_day1.sh setup         # enable APIs, create Firestore, stash secrets
#   ./scripts/sprint1_day1.sh verify        # check setup landed; ping Elastic
#   ./scripts/sprint1_day1.sh helloworld    # run agent/main.py against Elastic MCP
#   ./scripts/sprint1_day1.sh all           # preflight → setup → verify → helloworld

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env.local ]]; then
  # shellcheck disable=SC1091
  set -a; source .env.local; set +a
fi

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env.local}"
: "${GCP_REGION:=us-central1}"
: "${ELASTIC_ENDPOINT:?Set ELASTIC_ENDPOINT in .env.local (e.g. https://your-cluster.es.region.gcp.elastic-cloud.com)}"
: "${ELASTIC_API_KEY:?Set ELASTIC_API_KEY in .env.local (base64 API key from Elastic Cloud)}"

REQUIRED_APIS=(
  aiplatform.googleapis.com           # Vertex AI / Gemini
  run.googleapis.com                  # Cloud Run (verifier UI, standing-query job)
  firestore.googleapis.com            # Pending verifier queue + open cases
  secretmanager.googleapis.com        # Elastic API key, Mapbox token, webhook HMAC
  translate.googleapis.com            # Cloud Translation (via Agent Builder Extension)
  cloudbuild.googleapis.com           # Required for `gcloud run deploy --source`
  artifactregistry.googleapis.com     # Container images
  logging.googleapis.com              # Cloud Logging
  cloudtrace.googleapis.com           # Cloud Trace
)

# ─────────────────────────────────────────────────────────────────────────────
# preflight
# ─────────────────────────────────────────────────────────────────────────────
cmd_preflight() {
  echo "→ preflight: checking local tools"
  local missing=0
  for tool in gcloud uv jq curl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "  ✗ $tool not found"; missing=1
    else
      echo "  ✓ $tool ($(command -v "$tool"))"
    fi
  done
  if (( missing )); then
    echo "Install missing tools and re-run. macOS: brew install google-cloud-sdk jq; uv via https://docs.astral.sh/uv/"
    exit 1
  fi

  echo "→ preflight: gcloud auth"
  if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "  ✗ not authenticated. Run: gcloud auth login && gcloud auth application-default login"
    exit 1
  fi
  echo "  ✓ authenticated as $(gcloud config get-value account 2>/dev/null)"

  echo "→ preflight: project access"
  if ! gcloud projects describe "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "  ✗ cannot access project $GCP_PROJECT_ID. Check the id and your permissions."
    exit 1
  fi
  echo "  ✓ project $GCP_PROJECT_ID accessible"

  gcloud config set project "$GCP_PROJECT_ID" >/dev/null
}

# ─────────────────────────────────────────────────────────────────────────────
# setup (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
cmd_setup() {
  echo "→ setup: enabling Google Cloud APIs"
  gcloud services enable "${REQUIRED_APIS[@]}" --project="$GCP_PROJECT_ID"
  echo "  ✓ APIs enabled"

  echo "→ setup: Firestore (Native mode) in $GCP_REGION"
  if gcloud firestore databases describe --database="(default)" --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "  ✓ Firestore default database already exists"
  else
    gcloud firestore databases create \
      --location="$GCP_REGION" \
      --type=firestore-native \
      --project="$GCP_PROJECT_ID"
    echo "  ✓ Firestore created"
  fi

  echo "→ setup: stash Elastic API key in Secret Manager"
  if gcloud secrets describe elastic-api-key --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    echo "  ↻ secret exists; adding new version"
    printf '%s' "$ELASTIC_API_KEY" | gcloud secrets versions add elastic-api-key \
      --data-file=- --project="$GCP_PROJECT_ID" >/dev/null
  else
    printf '%s' "$ELASTIC_API_KEY" | gcloud secrets create elastic-api-key \
      --replication-policy=automatic --data-file=- --project="$GCP_PROJECT_ID"
  fi
  echo "  ✓ elastic-api-key stored"

  echo "→ setup: stash Elastic endpoint in Secret Manager (for symmetry)"
  if gcloud secrets describe elastic-endpoint --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
    printf '%s' "$ELASTIC_ENDPOINT" | gcloud secrets versions add elastic-endpoint \
      --data-file=- --project="$GCP_PROJECT_ID" >/dev/null
  else
    printf '%s' "$ELASTIC_ENDPOINT" | gcloud secrets create elastic-endpoint \
      --replication-policy=automatic --data-file=- --project="$GCP_PROJECT_ID"
  fi
  echo "  ✓ elastic-endpoint stored"

  echo "→ setup: install Python deps via uv"
  uv sync
  echo "  ✓ deps installed"
}

# ─────────────────────────────────────────────────────────────────────────────
# verify
# ─────────────────────────────────────────────────────────────────────────────
cmd_verify() {
  echo "→ verify: enabled APIs"
  local enabled; enabled=$(gcloud services list --enabled --project="$GCP_PROJECT_ID" --format="value(config.name)")
  for api in "${REQUIRED_APIS[@]}"; do
    if grep -q "^$api$" <<<"$enabled"; then
      echo "  ✓ $api"
    else
      echo "  ✗ $api NOT enabled"; exit 1
    fi
  done

  echo "→ verify: Firestore reachable"
  gcloud firestore databases describe --database="(default)" --project="$GCP_PROJECT_ID" \
    --format="value(name)" >/dev/null
  echo "  ✓ Firestore default database present"

  echo "→ verify: Secret Manager contents"
  for secret in elastic-api-key elastic-endpoint; do
    if gcloud secrets versions access latest --secret="$secret" --project="$GCP_PROJECT_ID" >/dev/null 2>&1; then
      echo "  ✓ $secret readable"
    else
      echo "  ✗ $secret missing or unreadable"; exit 1
    fi
  done

  echo "→ verify: Elastic cluster connectivity (cluster info)"
  local code
  code=$(curl -s -o /tmp/disasterlens_elastic_info.json -w "%{http_code}" \
    -H "Authorization: ApiKey $ELASTIC_API_KEY" \
    "$ELASTIC_ENDPOINT")
  if [[ "$code" == "200" ]]; then
    echo "  ✓ Elastic reachable — version $(jq -r .version.number /tmp/disasterlens_elastic_info.json 2>/dev/null || echo '?')"
  else
    echo "  ✗ Elastic returned HTTP $code (expected 200)"
    cat /tmp/disasterlens_elastic_info.json; echo
    exit 1
  fi

  echo "→ verify: Vertex AI / Gemini reachable from this account"
  if gcloud ai models list --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --limit=1 >/dev/null 2>&1; then
    echo "  ✓ Vertex AI list call succeeded"
  else
    echo "  ⚠  Vertex AI list call failed — check IAM (roles/aiplatform.user) on $(gcloud config get-value account)"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# helloworld — proves the ADK ↔ Elastic MCP round-trip
# ─────────────────────────────────────────────────────────────────────────────
cmd_helloworld() {
  echo "→ helloworld: running agent/main.py"
  echo "   (expects to discover Elastic Agent Builder MCP tools and list available indices)"
  uv run python -m agent.main
}

# ─────────────────────────────────────────────────────────────────────────────
cmd="${1:-all}"
case "$cmd" in
  preflight)   cmd_preflight ;;
  setup)       cmd_preflight; cmd_setup ;;
  verify)      cmd_verify ;;
  helloworld)  cmd_helloworld ;;
  all)         cmd_preflight; cmd_setup; cmd_verify; cmd_helloworld ;;
  *)           echo "usage: $0 {preflight|setup|verify|helloworld|all}"; exit 1 ;;
esac

echo
echo "✓ done: $cmd"
