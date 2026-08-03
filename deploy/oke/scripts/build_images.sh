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

: "${OCI_REGION_KEY:?Set OCI_REGION_KEY, for example gru, iad, phx}"
: "${OCI_TENANCY_NAMESPACE:?Set OCI_TENANCY_NAMESPACE}"
: "${OCIR_REPOSITORY_PREFIX:=agent-platform-oci}"
: "${IMAGE_TAG:=latest}"

REGISTRY="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}"

echo "Building images with root context: $ROOT_DIR"
echo "Registry prefix: $REGISTRY"

docker build -f "$ROOT_DIR/deploy/oke/dockerfiles/Dockerfile.agent-template-backend" -t "$REGISTRY/agent-template-backend:$IMAGE_TAG" "$ROOT_DIR"
docker build -f "$ROOT_DIR/deploy/oke/dockerfiles/Dockerfile.agent-gateway" -t "$REGISTRY/agent-gateway:$IMAGE_TAG" "$ROOT_DIR"
docker build -f "$ROOT_DIR/deploy/oke/dockerfiles/Dockerfile.channel-gateway" -t "$REGISTRY/channel-gateway:$IMAGE_TAG" "$ROOT_DIR"
docker build -f "$ROOT_DIR/deploy/oke/dockerfiles/Dockerfile.mcp-gateway" -t "$REGISTRY/mcp-gateway:$IMAGE_TAG" "$ROOT_DIR"
docker build -f "$ROOT_DIR/deploy/oke/dockerfiles/Dockerfile.agent-frontend" -t "$REGISTRY/agent-frontend:$IMAGE_TAG" "$ROOT_DIR"

echo "Images built:"
echo "$REGISTRY/agent-template-backend:$IMAGE_TAG"
echo "$REGISTRY/agent-gateway:$IMAGE_TAG"
echo "$REGISTRY/channel-gateway:$IMAGE_TAG"
echo "$REGISTRY/mcp-gateway:$IMAGE_TAG"
echo "$REGISTRY/agent-frontend:$IMAGE_TAG"
