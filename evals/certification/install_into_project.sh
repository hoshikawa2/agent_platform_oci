#!/usr/bin/env bash
set -euo pipefail
TARGET="${1:-.}"
mkdir -p "$TARGET/load" "$TARGET/playwright" "$TARGET/bin" "$TARGET/evidencias"
cp -R bin "$TARGET/"
cp -R load "$TARGET/"
cp -R playwright "$TARGET/"
cp run_certification.sh "$TARGET/"
chmod +x "$TARGET/run_certification.sh" "$TARGET/bin/certify_agent_platform.py"
echo "Instalado em $TARGET"
echo "Execute: cd $TARGET && ./run_certification.sh"
