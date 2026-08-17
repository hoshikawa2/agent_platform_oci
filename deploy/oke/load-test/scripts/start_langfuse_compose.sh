#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
[[ -f "$LT/.env.langfuse" ]] || "$LT/scripts/prepare_env.sh"
docker compose \
  --env-file "$LT/.env.langfuse" \
  -f "$ROOT/libs/agent_framework/Infrastructure_Langfuse/docker-compose.yml" \
  up -d
echo "Local Langfuse: http://localhost:3005"
echo "Keys are synchronized in $LT/.env.langfuse and $LT/.env.runtime"
