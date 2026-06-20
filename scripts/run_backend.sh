#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../agent_template_backend"
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework --no-build-isolation || pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000
