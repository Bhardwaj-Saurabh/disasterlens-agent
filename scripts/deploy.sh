#!/usr/bin/env bash
# Deploy DisasterLens to Cloud Run.
#
# Two services (verifier-ui + voice-gateway) plus one job (incident-stream).
# Each service gets --min-instances=1 to dodge the cold-start spike when a
# judge clicks the live URL during evaluation. That costs ~$3-5/day each,
# which is fine for hackathon judging week.
#
# Required env (caller's shell):
#   GCP_PROJECT_ID   e.g. disasterlens-2026
#   GCP_REGION       default us-central1
#
# Required secrets (already in Secret Manager from sprint1_day1.sh setup):
#   elastic-endpoint, elastic-api-key, kibana-endpoint
#
# Usage:
#   ./scripts/deploy.sh all          # build + push + deploy everything
#   ./scripts/deploy.sh verifier-ui  # just the chat / verifier service
#   ./scripts/deploy.sh voice        # just the Twilio gateway
#   ./scripts/deploy.sh job          # just the incident-stream job
#   ./scripts/deploy.sh check        # post-deploy: print URLs + curl health

set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID not set}"
REGION="${GCP_REGION:-us-central1}"
AR_REPO="${AR_REPO:-disasterlens}"
TAG="${TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"

UI_IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/verifier-ui:${TAG}"
VOICE_IMAGE="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/voice-gateway:${TAG}"

ensure_ar_repo() {
  if ! gcloud artifacts repositories describe "${AR_REPO}" \
      --location="${REGION}" --project="${GCP_PROJECT_ID}" >/dev/null 2>&1; then
    echo "▸ creating Artifact Registry repo ${AR_REPO}"
    gcloud artifacts repositories create "${AR_REPO}" \
      --repository-format=docker --location="${REGION}" \
      --project="${GCP_PROJECT_ID}" --description="DisasterLens container images"
  fi
}

build_ui() {
  ensure_ar_repo
  echo "▸ building ${UI_IMAGE}"
  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --tag="${UI_IMAGE}" \
    --config=- <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build', '-f', 'Dockerfile.verifier_ui', '-t', '${UI_IMAGE}', '.']
images: ['${UI_IMAGE}']
EOF
}

build_voice() {
  ensure_ar_repo
  echo "▸ building ${VOICE_IMAGE}"
  gcloud builds submit \
    --project="${GCP_PROJECT_ID}" \
    --tag="${VOICE_IMAGE}" \
    --config=- <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build', '-f', 'Dockerfile.voice_gateway', '-t', '${VOICE_IMAGE}', '.']
images: ['${VOICE_IMAGE}']
EOF
}

deploy_ui() {
  echo "▸ deploying verifier-ui (min-instances=1 to absorb judging cold-start)"
  gcloud run deploy verifier-ui \
    --image="${UI_IMAGE}" \
    --region="${REGION}" --project="${GCP_PROJECT_ID}" \
    --platform=managed --allow-unauthenticated \
    --memory=1Gi --cpu=2 \
    --min-instances=1 --max-instances=4 \
    --timeout=300 --concurrency=20 \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${GCP_PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GEMINI_MODEL=gemini-2.5-flash" \
    --set-secrets="ELASTIC_ENDPOINT=elastic-endpoint:latest,ELASTIC_API_KEY=elastic-api-key:latest,KIBANA_ENDPOINT=kibana-endpoint:latest"
}

deploy_voice() {
  echo "▸ deploying voice-gateway (min-instances=1; Twilio webhook timeouts are tight)"
  gcloud run deploy voice-gateway \
    --image="${VOICE_IMAGE}" \
    --region="${REGION}" --project="${GCP_PROJECT_ID}" \
    --platform=managed --allow-unauthenticated \
    --memory=1Gi --cpu=2 \
    --min-instances=1 --max-instances=2 \
    --timeout=300 --concurrency=10 \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${GCP_PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GEMINI_MODEL=gemini-2.5-flash" \
    --set-secrets="ELASTIC_ENDPOINT=elastic-endpoint:latest,ELASTIC_API_KEY=elastic-api-key:latest,KIBANA_ENDPOINT=kibana-endpoint:latest,TWILIO_ACCOUNT_SID=twilio-account-sid:latest,TWILIO_AUTH_TOKEN=twilio-auth-token:latest,TWILIO_FROM_NUMBER=twilio-from-number:latest"
}

deploy_job() {
  echo "▸ deploying incident-stream as a Cloud Run Job (run on demand for live demo)"
  gcloud run jobs deploy incident-stream \
    --image="${UI_IMAGE}" \
    --region="${REGION}" --project="${GCP_PROJECT_ID}" \
    --task-timeout=600 --max-retries=0 \
    --command="uv" \
    --args="run,python,-m,scripts.incident_stream,--period-sec,8" \
    --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},INCIDENT_STREAM_MODE=cloudrun,STREAM_MAX_DOCS=12" \
    --set-secrets="ELASTIC_ENDPOINT=elastic-endpoint:latest,ELASTIC_API_KEY=elastic-api-key:latest"
}

check() {
  echo "▸ verifier-ui URL:"
  ui_url=$(gcloud run services describe verifier-ui \
    --region="${REGION}" --project="${GCP_PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null || echo "(not deployed)")
  echo "    ${ui_url}"
  echo "▸ voice-gateway URL:"
  voice_url=$(gcloud run services describe voice-gateway \
    --region="${REGION}" --project="${GCP_PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null || echo "(not deployed)")
  echo "    ${voice_url}"
  echo "▸ cold-start probe (5 fresh curls of /healthz, first ≈ cold-start time):"
  if [[ "${ui_url}" =~ ^https ]]; then
    for i in 1 2 3 4 5; do
      printf "    %d: " "$i"
      curl -o /dev/null -s -w 'status=%{http_code}  total=%{time_total}s\n' \
        "${ui_url}/healthz" || true
      sleep 1
    done
  fi
}

case "${1:-all}" in
  all)         build_ui; build_voice; deploy_ui; deploy_voice; deploy_job; check ;;
  verifier-ui) build_ui; deploy_ui; check ;;
  voice)       build_voice; deploy_voice; check ;;
  job)         build_ui; deploy_job ;;
  check)       check ;;
  *)
    echo "usage: $0 {all|verifier-ui|voice|job|check}" >&2
    exit 1
    ;;
esac
