#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/mcp_gateway"
uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload
