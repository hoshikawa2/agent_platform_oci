#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
ENV="$LT/.env.runtime"

[[ -f "$ENV" ]] || { echo "ERROR: runtime env not found: $ENV" >&2; exit 1; }

# Keep variables local to this shell; do not export everything to kubectl/OCI CLI.
source "$ENV"

log() { printf '[deploy-backend] %s\n' "$*"; }
die() { printf '[deploy-backend] ERROR: %s\n' "$*" >&2; exit 1; }

command -v kubectl >/dev/null 2>&1 || die "kubectl not found in PATH"

NS="${K8S_NAMESPACE:-agent-load-test}"
OCIR_SECRET_NAME="${OCIR_PULL_SECRET_NAME:-ocir-secret}"

IMAGE="$(cat "$LT/.backend-image" 2>/dev/null || true)"
[[ -n "$IMAGE" ]] || IMAGE="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}/agent-template-backend:${IMAGE_TAG}"

log "Namespace: $NS"
log "Backend image: $IMAGE"

log "Checking Kubernetes API authentication..."
kubectl get --raw='/readyz' >/dev/null 2>&1 || die "Kubernetes API authentication failed"
kubectl get --raw='/openapi/v2' >/dev/null 2>&1 || die "Kubernetes OpenAPI access failed"

log "Ensuring namespace exists..."
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

: "${OCI_REGION_KEY:?OCI_REGION_KEY must be set in $ENV}"
: "${OCIR_USERNAME:?OCIR_USERNAME must be set in $ENV}"
: "${OCIR_AUTH_TOKEN:?OCIR_AUTH_TOKEN must be set in $ENV}"

OCIR_EMAIL="${OCIR_EMAIL:-unused@example.invalid}"
OCIR_SERVER="${OCI_REGION_KEY}.ocir.io"

log "Creating/updating OCIR pull secret '$OCIR_SECRET_NAME'..."
kubectl create secret docker-registry "$OCIR_SECRET_NAME"   -n "$NS"   --docker-server="$OCIR_SERVER"   --docker-username="$OCIR_USERNAME"   --docker-password="$OCIR_AUTH_TOKEN"   --docker-email="$OCIR_EMAIL"   --dry-run=client -o yaml | kubectl apply -f - >/dev/null

log "Associating OCIR pull secret with ServiceAccount/default..."
kubectl patch serviceaccount default   -n "$NS"   --type=merge   -p "{\"imagePullSecrets\":[{\"name\":\"${OCIR_SECRET_NAME}\"}]}" >/dev/null

pull_secret="$(kubectl get serviceaccount default -n "$NS" -o jsonpath='{.imagePullSecrets[*].name}')"
[[ " $pull_secret " == *" $OCIR_SECRET_NAME "* ]] || die "ServiceAccount/default does not reference $OCIR_SECRET_NAME"

log "Creating/updating backend runtime secret..."
"$LT/scripts/create_runtime_secret.sh"

if [[ "${ENABLE_LANGFUSE:-true}" == "true" ]]; then
  log "Synchronizing Langfuse client credentials..."
  "$LT/scripts/sync_langfuse_client_secret.sh"
fi

log "Creating/updating backend wallet secret..."
"$LT/scripts/create_wallet_secret.sh"

RUNTIME_CHECKSUM="$(cat "$LT/.env.runtime" "$LT/.env.langfuse" 2>/dev/null | sha256sum | awk '{print $1}')"
NODE_PORT="${BACKEND_NODE_PORT:-32116}"

log "Applying backend Kubernetes manifest..."
sed   -e "s#namespace: agent-load-test#namespace: $NS#g"   -e "s#name: agent-load-test#name: $NS#g"   -e "s#IMAGE_PLACEHOLDER#$IMAGE#g"   -e "s#replicas: 4#replicas: ${LOADTEST_MIN_REPLICAS:-4}#"   -e "s#minReplicas: 4#minReplicas: ${LOADTEST_MIN_REPLICAS:-4}#"   -e "s#maxReplicas: 30#maxReplicas: ${LOADTEST_MAX_REPLICAS:-30}#"   -e "s#cpu: \"500m\"#cpu: \"${LOADTEST_CPU_REQUEST:-500m}\"#"   -e "s#cpu: \"2000m\"#cpu: \"${LOADTEST_CPU_LIMIT:-2000m}\"#"   -e "s#memory: \"768Mi\"#memory: \"${LOADTEST_MEMORY_REQUEST:-768Mi}\"#"   -e "s#memory: \"2Gi\"#memory: \"${LOADTEST_MEMORY_LIMIT:-2Gi}\"#"   -e "s#RUNTIME_CHECKSUM_PLACEHOLDER#$RUNTIME_CHECKSUM#g"   -e "s#NODE_PORT_PLACEHOLDER#$NODE_PORT#g"   "$LT/k8s/agent-backend.yaml" | kubectl apply -f -

log "Waiting for backend rollout..."
if ! kubectl -n "$NS" rollout status deployment/agent-template-backend --timeout=10m; then
  echo "================ BACKEND ROLLOUT FAILED ================" >&2
  kubectl -n "$NS" get pods -o wide >&2 || true
  bad_pod="$(kubectl -n "$NS" get pods -l app=agent-template-backend --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null || true)"
  if [[ -n "$bad_pod" ]]; then
    kubectl -n "$NS" describe pod "$bad_pod" >&2 || true
    kubectl -n "$NS" logs "$bad_pod" -c agent-template-backend --tail=200 >&2 || true
  fi
  exit 1
fi

log "Final backend pods:"
kubectl -n "$NS" get pods -o wide

log "Backend NodePort service (fronted by existing OCI LB):"
kubectl -n "$NS" get svc agent-template-backend-lb

log "Backend HPA:"
kubectl -n "$NS" get hpa

log "Default ServiceAccount imagePullSecrets:"
kubectl -n "$NS" get serviceaccount default -o jsonpath='{.imagePullSecrets[*].name}{"\n"}'

log "Backend deployment completed successfully."
