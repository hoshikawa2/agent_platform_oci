#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REPOSITORY:?Informe GITHUB_REPOSITORY. Ex: org/agent_platform_oci}"
: "${GITHUB_TOKEN:?Informe GITHUB_TOKEN com permissão contents:write}"
: "${PACKAGE_VERSION:?Informe PACKAGE_VERSION. Ex: 1.0.0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DIST_DIR="${ROOT_DIR}/libs/agent_framework/dist"
TAG="agent-framework-v${PACKAGE_VERSION}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI não encontrado. Instale gh ou use o workflow GitHub Actions incluído."
  exit 1
fi

if [ ! -d "${DIST_DIR}" ] || [ -z "$(ls -A "${DIST_DIR}" 2>/dev/null || true)" ]; then
  echo "Dist não encontrado. Execute build_agent_framework.sh primeiro."
  exit 1
fi

export GH_TOKEN="${GITHUB_TOKEN}"
gh release create "${TAG}" "${DIST_DIR}"/* \
  --repo "${GITHUB_REPOSITORY}" \
  --title "agent-framework ${PACKAGE_VERSION}" \
  --notes "Wheel/sdist do agent-framework ${PACKAGE_VERSION}."

echo "Release criada: ${TAG}"
