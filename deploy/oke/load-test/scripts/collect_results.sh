#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
set -a; source "$LT/.env.runtime"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$LT/results/$STAMP"
mkdir -p "$OUT"
kubectl -n "$NS" get pods -o wide > "$OUT/pods.txt"
kubectl -n "$NS" get hpa -o yaml > "$OUT/hpa.yaml"
kubectl -n "$NS" get deploy agent-template-backend -o yaml > "$OUT/deployment.yaml"
kubectl -n "$NS" get svc -o wide > "$OUT/services.txt"
kubectl -n "$NS" top pods > "$OUT/top-pods.txt" 2>&1 || true
kubectl top nodes > "$OUT/top-nodes.txt" 2>&1 || true
kubectl -n "$NS" logs job/agent-load-generator > "$OUT/k6.log" 2>&1 || true
kubectl -n "$NS" logs -l app=agent-template-backend --prefix --tail=5000 > "$OUT/backend.log" 2>&1 || true
kubectl -n "$NS" get events --sort-by='.lastTimestamp' > "$OUT/events.txt" 2>&1 || true
echo "$OUT"
