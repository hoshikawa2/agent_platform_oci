#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
FRAMEWORK_DIR="${ROOT_DIR}/libs/agent_framework"

cd "${FRAMEWORK_DIR}"
python -m pip install --upgrade pip build twine
rm -rf dist build *.egg-info src/*.egg-info
python -m build
python -m twine check dist/*

echo "Build concluído em: ${FRAMEWORK_DIR}/dist"
ls -lh dist
