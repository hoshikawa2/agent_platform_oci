#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"
ENV_FILE="${ENV_FILE:-.env}"
LOAD_VUS="${LOAD_VUS:-5}"
LOAD_REQUESTS_PER_VU="${LOAD_REQUESTS_PER_VU:-2}"
EVIDENCE_DIR="${EVIDENCE_DIR:-evidencias/$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$EVIDENCE_DIR"

echo "== Agent Platform Certification =="
echo "Backend.....: $BACKEND_URL"
echo "Frontend....: $FRONTEND_URL"
echo "Env file....: $ENV_FILE"
echo "Evidências..: $EVIDENCE_DIR"
echo

python3 "$(dirname "$0")/bin/certify_agent_platform.py" \
  --base-url "$BACKEND_URL" \
  --frontend-url "$FRONTEND_URL" \
  --env-file "$ENV_FILE" \
  --evidence-dir "$EVIDENCE_DIR" \
  --load-vus "$LOAD_VUS" \
  --load-requests-per-vu "$LOAD_REQUESTS_PER_VU" "$@"
