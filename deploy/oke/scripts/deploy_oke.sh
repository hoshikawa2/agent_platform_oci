#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/oke/examples/oke.env.example}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

: "${OCI_REGION_KEY:?Set OCI_REGION_KEY}"
: "${OCI_TENANCY_NAMESPACE:?Set OCI_TENANCY_NAMESPACE}"
: "${OCIR_REPOSITORY_PREFIX:=agent-platform-oci}"
: "${IMAGE_TAG:=latest}"

NS="${K8S_NAMESPACE:-agent-platform}"
REGISTRY="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -n "${OKE_CLUSTER_OCID:-}" && -n "${OCI_REGION:-}" ]]; then
  echo "Updating kubeconfig for OKE cluster $OKE_CLUSTER_OCID"
  oci ce cluster create-kubeconfig \
    --cluster-id "$OKE_CLUSTER_OCID" \
    --file "$HOME/.kube/config" \
    --region "$OCI_REGION" \
    --token-version 2.0.0 \
    --kube-endpoint PUBLIC_ENDPOINT \
    ${OCI_CLI_PROFILE:+--profile "$OCI_CLI_PROFILE"} || true
fi

"$ROOT_DIR/deploy/oke/scripts/create_runtime_secret.sh" "$ENV_FILE"

cp -R "$ROOT_DIR/deploy/oke/k8s/base"/* "$TMP_DIR/"

cat > "$TMP_DIR/kustomization.yaml" <<EOF2
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - 00-namespace.yaml
  - 01-configmap.yaml
  - 03-agent-template-backend.yaml
  - 04-agent-gateway.yaml
  - 05-channel-gateway.yaml
  - 06-mcp-gateway.yaml
  - 07-frontend.yaml
images:
  - name: agent-template-backend
    newName: $REGISTRY/agent-template-backend
    newTag: $IMAGE_TAG
  - name: agent-gateway
    newName: $REGISTRY/agent-gateway
    newTag: $IMAGE_TAG
  - name: channel-gateway
    newName: $REGISTRY/channel-gateway
    newTag: $IMAGE_TAG
  - name: mcp-gateway
    newName: $REGISTRY/mcp-gateway
    newTag: $IMAGE_TAG
  - name: agent-frontend
    newName: $REGISTRY/agent-frontend
    newTag: $IMAGE_TAG
EOF2

kubectl apply -k "$TMP_DIR"
kubectl -n "$NS" rollout status deploy/agent-template-backend --timeout=180s
kubectl -n "$NS" rollout status deploy/agent-gateway --timeout=180s
kubectl -n "$NS" rollout status deploy/channel-gateway --timeout=180s
kubectl -n "$NS" rollout status deploy/mcp-gateway --timeout=180s
kubectl -n "$NS" rollout status deploy/agent-frontend --timeout=180s

kubectl -n "$NS" get svc
