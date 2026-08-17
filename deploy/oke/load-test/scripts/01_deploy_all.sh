#!/usr/bin/env bash
set -Eeuo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$DIR/deploy_langfuse.sh"
"$DIR/build_push_backend.sh"
"$DIR/deploy_backend.sh"
"$DIR/configure_existing_lb.sh"
"$DIR/validate_dependencies.sh"
"$DIR/smoke_test.sh" external
