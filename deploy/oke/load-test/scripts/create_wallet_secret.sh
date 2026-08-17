#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
WALLET="$ROOT/templates/agent_template_backend/wallet"
set -a; source "$ENV"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
mapfile -t wallet_files < <(find "$WALLET" -maxdepth 1 -type f ! -name 'README_PLACE_WALLET_HERE.txt' ! -name '.gitkeep')
if (( ${#wallet_files[@]} == 0 )); then
  echo "No real wallet files found in $WALLET"
  echo "Copy the Autonomous wallet files there, then rerun."
  exit 2
fi
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
args=()
for f in "${wallet_files[@]}"; do args+=("--from-file=$(basename "$f")=$f"); done
kubectl -n "$NS" create secret generic agent-backend-wallet "${args[@]}" --dry-run=client -o yaml | kubectl apply -f -
echo "Wallet secret agent-backend-wallet created/updated in namespace $NS"
