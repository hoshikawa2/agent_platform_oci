#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
[[ -f "$ENV" ]] || { echo "Run prepare_env.sh first"; exit 1; }
set -a; source "$ENV"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" create secret generic agent-backend-runtime --from-env-file="$ENV" --dry-run=client -o yaml | kubectl apply -f -
echo "Runtime env loaded into secret agent-backend-runtime."
