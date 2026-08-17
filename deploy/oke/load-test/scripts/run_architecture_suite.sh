#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
ENV="$LT/.env.runtime"
[[ -f "$ENV" ]] || "$LT/scripts/prepare_env.sh"
set -a; source "$ENV"; set +a

run_case() {
  local name="$1" rps="$2" dur="$3" scenario="$4"
  echo "=== $name: ${rps} rps / ${dur} / ${scenario} ==="
  python3 - "$ENV" "$rps" "$dur" "$scenario" <<'PY'
import sys
p,rps,dur,scenario=sys.argv[1:]
kv={}
order=[]
for line in open(p):
    if '=' in line and not line.startswith('#'):
        k,v=line.rstrip('\n').split('=',1); kv[k]=v; order.append(k)
kv['LOADTEST_RPS']=rps; kv['LOADTEST_DURATION']=dur; kv['LOADTEST_SCENARIO']=scenario
for k in ('LOADTEST_RPS','LOADTEST_DURATION','LOADTEST_SCENARIO'):
    if k not in order: order.append(k)
with open(p,'w') as f:
    f.write('# Generated/updated load-test runtime env. Do not commit.\n')
    for k in order: f.write(f'{k}={kv[k]}\n')
PY
  "$LT/scripts/run_load_test.sh" internal
  kubectl -n "${K8S_NAMESPACE:-agent-load-test}" logs -f job/agent-load-generator || true
  "$LT/scripts/collect_results.sh"
}

run_case warmup 5 2m unique_sessions
run_case baseline 25 5m unique_sessions
run_case scale 100 10m unique_sessions
run_case shared-state 50 10m shared_sessions

echo "Suite completed. Review deploy/oke/load-test/results and Langfuse."
