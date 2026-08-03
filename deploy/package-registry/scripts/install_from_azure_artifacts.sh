#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_ORG:?Informe AZURE_ORG}"
: "${AZURE_PROJECT:?Informe AZURE_PROJECT}"
: "${AZURE_FEED:?Informe AZURE_FEED}"
: "${AZURE_PAT:?Informe AZURE_PAT com permissão Packaging Read}"
: "${AGENT_FRAMEWORK_VERSION:=0.1.0}"

INDEX_URL="https://azdo:${AZURE_PAT}@pkgs.dev.azure.com/${AZURE_ORG}/${AZURE_PROJECT}/_packaging/${AZURE_FEED}/pypi/simple/"
python -m pip install --upgrade pip
python -m pip install --index-url "${INDEX_URL}" --extra-index-url https://pypi.org/simple "agent-framework==${AGENT_FRAMEWORK_VERSION}"
