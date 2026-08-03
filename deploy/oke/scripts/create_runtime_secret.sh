#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/oke/examples/oke.env.example}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

NS="${K8S_NAMESPACE:-agent-platform}"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" create secret generic agent-platform-secrets \
  --from-literal=OCI_GENAI_BASE_URL="${OCI_GENAI_BASE_URL:-}" \
  --from-literal=OCI_GENAI_API_KEY="${OCI_GENAI_API_KEY:-}" \
  --from-literal=OCI_GENAI_MODEL="${OCI_GENAI_MODEL:-}" \
  --from-literal=OCI_GENAI_PROJECT_OCID="${OCI_GENAI_PROJECT_OCID:-}" \
  --from-literal=OCI_COMPARTMENT_ID="${OCI_COMPARTMENT_ID:-}" \
  --from-literal=OCI_REGION="${OCI_REGION:-}" \
  --from-literal=LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}" \
  --from-literal=LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}" \
  --from-literal=LANGFUSE_HOST="${LANGFUSE_HOST:-}" \
  --from-literal=MCP_GATEWAY_TOKEN="${MCP_GATEWAY_TOKEN:-}" \
  --dry-run=client -o yaml | kubectl apply -f -
