#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
BASE="$ROOT/templates/agent_template_backend/.env"
DEFAULTS="$LT/.env.loadtest.example"
OVERRIDE="$LT/.env.loadtest"

[[ -f "$BASE" ]] || { echo "ERROR: backend env not found: $BASE" >&2; exit 1; }
[[ -f "$DEFAULTS" ]] || { echo "ERROR: load-test defaults not found: $DEFAULTS" >&2; exit 1; }

args=(
  --base "$BASE"
  --overlay "$DEFAULTS"
  --output "$LT/.env.runtime"
  --langfuse-env "$LT/.env.langfuse"
)

if [[ -f "$OVERRIDE" ]]; then
  args+=(--override "$OVERRIDE")
  echo "Using explicit load-test overrides: $OVERRIDE"
else
  echo "No $OVERRIDE found; backend .env values will be preserved and example defaults only fill missing keys."
fi

python3 "$LT/scripts/prepare_env.py" "${args[@]}"

echo
echo "Runtime environment prepared: $LT/.env.runtime"
echo "Source of application configuration: $BASE"
echo "Optional explicit overrides: $OVERRIDE"
