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

REGISTRY="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}"

for image in agent-template-backend agent-gateway channel-gateway mcp-gateway agent-frontend; do
  docker push "$REGISTRY/$image:$IMAGE_TAG"
done
