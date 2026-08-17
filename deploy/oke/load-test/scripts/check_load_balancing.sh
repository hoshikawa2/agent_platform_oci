#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
set -a; source "$ROOT/deploy/oke/load-test/.env.runtime"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
IP="$(kubectl -n "$NS" get svc agent-template-backend-lb -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"
[[ -n "$IP" ]] || { echo "LoadBalancer IP not assigned"; exit 3; }
URL="http://${IP}:8000/health"
echo "Sampling 30 requests from $URL"
for i in $(seq 1 30); do
  curl -fsS -D - -o /dev/null "$URL" 2>/dev/null | awk -F': ' 'tolower($1)=="x-agent-pod" {gsub("\r", "", $2); print $2}'
done | sort | uniq -c | sort -nr
