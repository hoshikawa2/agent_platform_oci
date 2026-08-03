#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_ORG:?Informe AZURE_ORG. Ex: minha-org}"
: "${AZURE_PROJECT:?Informe AZURE_PROJECT. Ex: AgentPlatform}"
: "${AZURE_FEED:?Informe AZURE_FEED. Ex: agent-framework-feed}"
: "${AZURE_PAT:?Informe AZURE_PAT com permissão Packaging Read/Write}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DIST_DIR="${ROOT_DIR}/libs/agent_framework/dist"
PYPIRC_FILE="${ROOT_DIR}/deploy/package-registry/.pypirc.azure.generated"
REPOSITORY_URL="https://pkgs.dev.azure.com/${AZURE_ORG}/${AZURE_PROJECT}/_packaging/${AZURE_FEED}/pypi/upload/"

if [ ! -d "${DIST_DIR}" ] || [ -z "$(ls -A "${DIST_DIR}" 2>/dev/null || true)" ]; then
  echo "Dist não encontrado. Execute deploy/package-registry/scripts/build_agent_framework.sh primeiro."
  exit 1
fi

cat > "${PYPIRC_FILE}" <<PYPIRC
[distutils]
index-servers = azure

[azure]
repository = ${REPOSITORY_URL}
username = azdo
password = ${AZURE_PAT}
PYPIRC

python -m pip install --upgrade twine
python -m twine upload --config-file "${PYPIRC_FILE}" -r azure "${DIST_DIR}"/*
rm -f "${PYPIRC_FILE}"

echo "Publicado no Azure Artifacts: ${AZURE_ORG}/${AZURE_PROJECT}/${AZURE_FEED}"
