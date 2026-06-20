#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../apps/ai_gateway"
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload
