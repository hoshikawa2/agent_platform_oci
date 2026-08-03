#!/usr/bin/env bash
set -euo pipefail
NS="${K8S_NAMESPACE:-agent-platform}"
kubectl -n "$NS" get pods -o wide
kubectl -n "$NS" get hpa
kubectl -n "$NS" get svc
