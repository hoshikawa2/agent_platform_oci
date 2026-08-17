#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
ENV="$LT/.env.runtime"
[[ -f "$ENV" ]] && source "$ENV"

NS="${K8S_NAMESPACE:-agent-load-test}"
SERVICE_NAME="${BACKEND_SERVICE_NAME:-agent-template-backend-lb}"
LB_OCID="${EXISTING_LB_OCID:?EXISTING_LB_OCID must be set}"
BACKEND_SET="${BACKEND_SET_NAME:-agent-framework-loadtest}"
LISTENER_NAME="${BACKEND_LISTENER_NAME:-agent-framework-loadtest}"
LISTENER_PORT="${BACKEND_LISTENER_PORT:-8000}"
LISTENER_PROTOCOL="${BACKEND_LISTENER_PROTOCOL:-HTTP}"
BACKEND_POLICY="${BACKEND_POLICY:-ROUND_ROBIN}"
HEALTH_PATH="${BACKEND_HEALTH_PATH:-/health}"
OCI_PROFILE="${OCI_CLI_PROFILE:-}"

log(){ printf '[existing-lb] %s\n' "$*"; }
die(){ printf '[existing-lb] ERROR: %s\n' "$*" >&2; exit 1; }

OCI_ARGS=()
[[ -n "$OCI_PROFILE" ]] && OCI_ARGS+=(--profile "$OCI_PROFILE")
oci_lb(){ oci lb "$@" "${OCI_ARGS[@]}"; }

command -v oci >/dev/null || die "oci CLI not found"
command -v kubectl >/dev/null || die "kubectl not found"

log "Validating Load Balancer..."
oci_lb load-balancer get --load-balancer-id "$LB_OCID" >/dev/null

NODE_PORT="$(kubectl -n "$NS" get svc "$SERVICE_NAME" -o jsonpath='{.spec.ports[0].nodePort}')"
[[ -n "$NODE_PORT" && "$NODE_PORT" != "0" ]] || die "Service/$SERVICE_NAME has no NodePort"
log "NodePort=$NODE_PORT"

if oci_lb backend-set get --load-balancer-id "$LB_OCID" --backend-set-name "$BACKEND_SET" >/dev/null 2>&1; then
  log "Backend set '$BACKEND_SET' already exists"
else
  log "Creating backend set '$BACKEND_SET'..."
  oci_lb backend-set create \
    --load-balancer-id "$LB_OCID" \
    --name "$BACKEND_SET" \
    --policy "$BACKEND_POLICY" \
    --health-checker-protocol HTTP \
    --health-checker-port "$NODE_PORT" \
    --health-checker-url-path "$HEALTH_PATH" \
    --health-checker-return-code 200 \
    --health-checker-retries 3 \
    --health-checker-timeout-in-ms 3000 \
    --health-checker-interval-in-ms 10000 \
    --wait-for-state SUCCEEDED \
    --max-wait-seconds 1200 >/dev/null
fi

for i in $(seq 1 20); do
  oci_lb backend-set get --load-balancer-id "$LB_OCID" --backend-set-name "$BACKEND_SET" >/dev/null 2>&1 && break
  [[ "$i" == "20" ]] && die "backend set still unavailable"
  sleep 3
done

mapfile -t NODE_IPS < <(
  kubectl get nodes -o jsonpath='{range .items[*]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' |
  sed '/^$/d' | sort -u
)

EXISTING="$(oci_lb backend list \
  --load-balancer-id "$LB_OCID" \
  --backend-set-name "$BACKEND_SET" \
  --query 'data[].name' --raw-output 2>/dev/null || true)"

for ip in "${NODE_IPS[@]}"; do
  name="${ip}:${NODE_PORT}"
  if grep -Fxq "$name" <<<"$EXISTING"; then
    log "Backend $name already exists"
  else
    log "Creating backend $name..."
    oci_lb backend create \
      --load-balancer-id "$LB_OCID" \
      --backend-set-name "$BACKEND_SET" \
      --ip-address "$ip" \
      --port "$NODE_PORT" \
      --wait-for-state SUCCEEDED \
      --max-wait-seconds 1200 >/dev/null
  fi
done

listener_found="$(
  oci_lb load-balancer get \
    --load-balancer-id "$LB_OCID" \
    --query "data.listeners.\"${LISTENER_NAME}\".name" \
    --raw-output 2>/dev/null || true
)"

if [[ "$listener_found" == "$LISTENER_NAME" ]]; then
  log "Listener '$LISTENER_NAME' already exists"
else
  log "Creating listener '$LISTENER_NAME'..."
  oci_lb listener create \
    --load-balancer-id "$LB_OCID" \
    --name "$LISTENER_NAME" \
    --default-backend-set-name "$BACKEND_SET" \
    --port "$LISTENER_PORT" \
    --protocol "$LISTENER_PROTOCOL" \
    --wait-for-state SUCCEEDED \
    --max-wait-seconds 1200 >/dev/null
fi

log "Backends:"
oci_lb backend list \
  --load-balancer-id "$LB_OCID" \
  --backend-set-name "$BACKEND_SET" \
  --query 'data[].{name:name,ip:"ip-address",port:port}' \
  --output table

log "Backend set health:"
oci_lb backend-set-health get \
  --load-balancer-id "$LB_OCID" \
  --backend-set-name "$BACKEND_SET" \
  --output table || true

log "Done"
