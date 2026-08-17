#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
set -a; source "$ROOT/deploy/oke/load-test/.env.runtime"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
while true; do
  clear
  date
  echo '=== Pods ==='
  kubectl -n "$NS" get pods -o wide
  echo '=== HPA ==='
  kubectl -n "$NS" get hpa
  echo '=== Resource usage ==='
  kubectl -n "$NS" top pods 2>/dev/null || echo 'metrics-server not available'
  sleep 5
done
