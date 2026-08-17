#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
[[ -f "$ENV" ]] || { echo "Run prepare_env.sh first"; exit 1; }
set -a; source "$ENV"; set +a
oci ce cluster create-kubeconfig \
  --cluster-id "$OKE_CLUSTER_OCID" \
  --file "$HOME/.kube/config" \
  --region "$OCI_REGION" \
  --token-version 2.0.0 \
  --kube-endpoint PUBLIC_ENDPOINT \
  --profile "${OCI_CLI_PROFILE:-DEFAULT}"
kubectl cluster-info
kubectl get nodes -o wide
