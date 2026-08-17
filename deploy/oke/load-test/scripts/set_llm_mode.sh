#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ENV="$ROOT/deploy/oke/load-test/.env.runtime"
MODE="${1:-}"
case "$MODE" in
  mock) VALUE=mock ;;
  real|oci) VALUE=oci_sdk ;;
  *) echo "Usage: $0 mock|real"; exit 2 ;;
esac
python3 - "$ENV" "$VALUE" <<'PY'
import sys
p,v=sys.argv[1:]
lines=open(p).read().splitlines(); out=[]; found=False
for line in lines:
    if line.startswith('LLM_PROVIDER='):
        out.append('LLM_PROVIDER='+v); found=True
    else: out.append(line)
if not found: out.append('LLM_PROVIDER='+v)
open(p,'w').write('\n'.join(out)+'\n')
PY
set -a; source "$ENV"; set +a
NS="${K8S_NAMESPACE:-agent-load-test}"
kubectl -n "$NS" create secret generic agent-backend-runtime --from-env-file="$ENV" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NS" rollout restart deployment/agent-template-backend
kubectl -n "$NS" rollout status deployment/agent-template-backend --timeout=10m
echo "LLM_PROVIDER=$VALUE"
