#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/prepare_env.sh"
echo
cat <<'TXT'
Next:
1) edit deploy/oke/load-test/.env.runtime
2) copy the real Autonomous wallet into templates/agent_template_backend/wallet/
3) run configure_kubeconfig.sh
TXT
