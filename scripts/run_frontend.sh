#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../agent_frontend"
python -m http.server 5173
