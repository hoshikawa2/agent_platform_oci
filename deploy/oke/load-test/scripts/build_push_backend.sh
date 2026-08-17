#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
set -a; source "$ENV"; set +a
IMAGE="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}/agent-template-backend:${IMAGE_TAG}"
echo "Building $IMAGE"
docker build -f "$ROOT/deploy/oke/dockerfiles/Dockerfile.agent-template-backend" -t "$IMAGE" "$ROOT"
docker push "$IMAGE"
echo "$IMAGE" > "$ROOT/deploy/oke/load-test/.backend-image"
