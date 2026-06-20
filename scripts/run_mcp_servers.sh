#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python -m venv "$ROOT/.venv"
source "$ROOT/.venv/bin/activate"
pip install -r "$ROOT/mcp_servers/telecom_mcp_server/requirements.txt"
pip install -r "$ROOT/mcp_servers/retail_mcp_server/requirements.txt"

uvicorn --app-dir "$ROOT/mcp_servers/telecom_mcp_server" main:app --host 0.0.0.0 --port 8100 &
PID1=$!
uvicorn --app-dir "$ROOT/mcp_servers/retail_mcp_server" main:app --host 0.0.0.0 --port 8200 &
PID2=$!

echo "Telecom MCP em http://localhost:8100"
echo "Retail MCP em http://localhost:8200"
trap 'kill $PID1 $PID2' INT TERM EXIT
wait
