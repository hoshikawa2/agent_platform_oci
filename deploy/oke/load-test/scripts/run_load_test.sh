#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
ENV="$LT/.env.runtime"
[[ -f "$ENV" ]] || { echo "ERROR: $ENV not found" >&2; exit 1; }
source "$ENV"

NS="${K8S_NAMESPACE:-agent-load-test}"
TARGET_MODE="${1:-${LOADTEST_TARGET_MODE:-internal}}"

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

case "$TARGET_MODE" in
  external)
    LOADTEST_TARGET="$(resolve_external_url)"
    ;;
  internal)
    LOADTEST_TARGET="http://agent-template-backend.${NS}.svc.cluster.local:8000"
    ;;
  *)
    echo "Usage: $0 [internal|external]" >&2
    exit 2
    ;;
esac

echo "Load-test mode: $TARGET_MODE"
echo "Load-test target: $LOADTEST_TARGET"

TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT
cp "$ENV" "$TMP_ENV"

python3 - "$TMP_ENV" "$LOADTEST_TARGET" "$TARGET_MODE" <<'PY'
import sys
p,target,mode=sys.argv[1:]
lines=[]
seen_target=False
seen_mode=False
for line in open(p):
    if line.startswith("LOADTEST_TARGET="):
        lines.append(f"LOADTEST_TARGET={target}\n")
        seen_target=True
    elif line.startswith("LOADTEST_TARGET_MODE="):
        lines.append(f"LOADTEST_TARGET_MODE={mode}\n")
        seen_mode=True
    else:
        lines.append(line)
if not seen_target:
    lines.append(f"LOADTEST_TARGET={target}\n")
if not seen_mode:
    lines.append(f"LOADTEST_TARGET_MODE={mode}\n")
open(p,"w").writelines(lines)
PY

kubectl -n "$NS" create secret generic agent-backend-runtime \
  --from-env-file="$TMP_ENV" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" create configmap k6-load-script \
  --from-file=loadtest.js="$LT/loadgen/loadtest.js" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" delete job agent-load-generator \
  --ignore-not-found --wait=true

sed \
  -e "s#namespace: agent-load-test#namespace: $NS#g" \
  "$LT/k8s/k6-job.yaml" | kubectl apply -f -

echo "Load test started against $LOADTEST_TARGET"
echo "Follow: kubectl -n $NS logs -f job/agent-load-generator"
echo "Watch:  watch kubectl -n $NS get pods,hpa"
