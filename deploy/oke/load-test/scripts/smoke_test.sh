#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
[[ -f "$ENV" ]] || { echo "ERROR: $ENV not found" >&2; exit 1; }
source "$ENV"

NS="${K8S_NAMESPACE:-agent-load-test}"
MODE="${1:-external}"

resolve_external_url() {
  if [[ -n "${LOADTEST_EXTERNAL_URL:-}" ]]; then
    printf '%s\n' "${LOADTEST_EXTERNAL_URL%/}"
    return 0
  fi

  : "${EXISTING_LB_OCID:?Set EXISTING_LB_OCID or LOADTEST_EXTERNAL_URL in .env.runtime}"

  command -v oci >/dev/null 2>&1 || {
    echo "ERROR: oci CLI not found and LOADTEST_EXTERNAL_URL is not set" >&2
    return 1
  }

  local oci_args=()
  [[ -n "${OCI_CLI_PROFILE:-}" ]] && oci_args+=(--profile "$OCI_CLI_PROFILE")

  local ip
  ip="$(
    oci lb load-balancer get \
      --load-balancer-id "$EXISTING_LB_OCID" \
      "${oci_args[@]}" \
      --query 'data."ip-addresses"[0]."ip-address"' \
      --raw-output
  )"

  [[ -n "$ip" && "$ip" != "null" ]] || {
    echo "ERROR: could not resolve IP from existing LB $EXISTING_LB_OCID" >&2
    return 1
  }

  local proto="${BACKEND_LISTENER_PROTOCOL:-HTTP}"
  local scheme
  scheme="$(printf '%s' "$proto" | tr '[:upper:]' '[:lower:]')"
  [[ "$scheme" == "http" || "$scheme" == "https" ]] || scheme="http"

  local port="${BACKEND_LISTENER_PORT:-8000}"
  printf '%s://%s:%s\n' "$scheme" "$ip" "$port"
}

if [[ "$MODE" == "external" ]]; then
  URL="$(resolve_external_url)"
elif [[ "$MODE" == "internal" ]]; then
  # Execute curl inside the cluster because *.svc.cluster.local is not resolvable
  # from the developer workstation.
  URL="http://agent-template-backend.${NS}.svc.cluster.local:8000"
else
  echo "Usage: $0 [external|internal]" >&2
  exit 2
fi

SID="smoke-$(date +%s)"
PAYLOAD="{\"channel\":\"web\",\"agent_id\":\"${LOADTEST_AGENT_ID:-telecom_contas}\",\"tenant_id\":\"loadtest\",\"payload\":{\"text\":\"Olá. Responda apenas OK.\",\"session_id\":\"$SID\",\"user_id\":\"smoke\",\"customer_id\":\"smoke\",\"message_id\":\"smoke-1\"}}"


verify_langfuse_trace() {
  [[ "${ENABLE_LANGFUSE:-true}" == "true" ]] || return 0
  local checkpod="langfuse-trace-check-$(date +%s)"
  local needle="$SID"
  echo "Verifying trace ingestion in Langfuse for session $needle ..."
  kubectl -n "$NS" delete pod "$checkpod" --ignore-not-found >/dev/null 2>&1 || true
  kubectl -n "$NS" run "$checkpod" --restart=Never --image=docker.io/curlimages/curl:latest \
    --overrides="$(cat <<JSON
{"spec":{"containers":[{"name":"$checkpod","image":"docker.io/curlimages/curl:latest","env":[
{"name":"LANGFUSE_HOST","valueFrom":{"secretKeyRef":{"name":"langfuse-client","key":"LANGFUSE_HOST"}}},
{"name":"LANGFUSE_PUBLIC_KEY","valueFrom":{"secretKeyRef":{"name":"langfuse-client","key":"LANGFUSE_PUBLIC_KEY"}}},
{"name":"LANGFUSE_SECRET_KEY","valueFrom":{"secretKeyRef":{"name":"langfuse-client","key":"LANGFUSE_SECRET_KEY"}}}
],"command":["sh","-c"],"args":["set -eu; i=0; while [ \$i -lt 12 ]; do body=\$(curl -fsS -u \"\$LANGFUSE_PUBLIC_KEY:\$LANGFUSE_SECRET_KEY\" \"\$LANGFUSE_HOST/api/public/traces?limit=100\" || true); echo \"\$body\" | grep -F '$needle' >/dev/null && { echo LANGFUSE_TRACE_OK; exit 0; }; i=\$((i+1)); sleep 5; done; echo LANGFUSE_TRACE_NOT_FOUND >&2; exit 1"]}]}}
JSON
)" >/dev/null
  if ! kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$checkpod" --timeout=90s >/dev/null 2>&1; then
    kubectl -n "$NS" logs "$checkpod" || true
    kubectl -n "$NS" delete pod "$checkpod" --ignore-not-found >/dev/null 2>&1 || true
    return 1
  fi
  kubectl -n "$NS" logs "$checkpod"
  kubectl -n "$NS" delete pod "$checkpod" --ignore-not-found >/dev/null
}

echo "Smoke target: $URL ($MODE)"

if [[ "$MODE" == "external" ]]; then
  echo "Health:"
  curl -fsS --connect-timeout 10 --max-time 30 "$URL/health"
  echo
  echo "Gateway message:"
  curl -fsS --connect-timeout 10 --max-time 120 \
    -X POST "$URL/gateway/message" \
    -H 'Content-Type: application/json' \
    -H "X-Request-ID: smoke-$SID" \
    -d "$PAYLOAD"
  echo
else
  pod="backend-smoke-$(date +%s)"
  kubectl -n "$NS" run "$pod" \
    --restart=Never \
    --image=docker.io/curlimages/curl:latest \
    --command -- sh -c \
    "set -e;
     echo 'Health:';
     curl -fsS --connect-timeout 10 --max-time 30 '$URL/health';
     echo;
     echo 'Gateway message:';
     curl -fsS --connect-timeout 10 --max-time 120 -X POST '$URL/gateway/message' \
       -H 'Content-Type: application/json' \
       -H 'X-Request-ID: smoke-$SID' \
       -d '$PAYLOAD';
     echo" >/dev/null

  if ! kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$pod" --timeout=180s >/dev/null 2>&1; then
    kubectl -n "$NS" logs "$pod" || true
    kubectl -n "$NS" describe pod "$pod" || true
    kubectl -n "$NS" delete pod "$pod" --ignore-not-found >/dev/null 2>&1 || true
    exit 1
  fi

  kubectl -n "$NS" logs "$pod"
  kubectl -n "$NS" delete pod "$pod" --ignore-not-found >/dev/null
fi

verify_langfuse_trace
