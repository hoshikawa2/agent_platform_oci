#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
RUNTIME_ENV="$LT/.env.runtime"

log(){ printf '[langfuse-validate] %s\n' "$*"; }
die(){ printf '[langfuse-validate] ERROR: %s\n' "$*" >&2; exit 1; }

# Do not source .env.runtime: OCI_* values can affect the OCI CLI exec plugin
# used by kubectl. Read only the values required by this validator.
read_env_value() {
  local file="$1" key="$2" default_value="${3:-}"
  local value=""
  if [[ -f "$file" ]]; then
    value="$(sed -n -E "s/^${key}=(.*)$/\\1/p" "$file" | tail -n 1)"
    value="${value%$'\r'}"
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then value="${value:1:${#value}-2}"; fi
    if [[ "$value" == \'*\' && "$value" == *\' ]]; then value="${value:1:${#value}-2}"; fi
  fi
  printf '%s\n' "${value:-$default_value}"
}

LF_NS="${LANGFUSE_NAMESPACE:-$(read_env_value "$RUNTIME_ENV" LANGFUSE_NAMESPACE langfuse)}"
APP_NS="${K8S_NAMESPACE:-$(read_env_value "$RUNTIME_ENV" K8S_NAMESPACE agent-load-test)}"
CLIENT_SECRET="${LANGFUSE_CLIENT_SECRET:-langfuse-client}"
LF_HOST="${LANGFUSE_HOST:-$(read_env_value "$RUNTIME_ENV" LANGFUSE_HOST "http://langfuse-web.${LF_NS}.svc.cluster.local:3000")}"
POD="langfuse-auth-check-$(date +%s)"

command -v kubectl >/dev/null 2>&1 || die "kubectl not found"

log "Kubernetes context: $(kubectl config current-context 2>/dev/null || echo '<unknown>')"

# Fail early with a Kubernetes-auth specific message.
if ! kubectl auth can-i get secrets -n "$LF_NS" >/dev/null 2>&1; then
  die "Kubernetes authentication/authorization failed. Confirm 'kubectl get nodes' works before validating Langfuse."
fi

"$LT/scripts/sync_langfuse_client_secret.sh"

cleanup(){
  kubectl -n "$APP_NS" delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Use a normal Pod manifest instead of `kubectl run --overrides`.
# This avoids JSON-patch escaping issues and keeps secretKeyRef explicit.
cat <<YAML | kubectl apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: ${APP_NS}
  labels:
    app: langfuse-auth-check
spec:
  restartPolicy: Never
  containers:
    - name: check
      image: docker.io/curlimages/curl:latest
      env:
        - name: LANGFUSE_HOST
          value: "${LF_HOST}"
        - name: LANGFUSE_PUBLIC_KEY
          valueFrom:
            secretKeyRef:
              name: ${CLIENT_SECRET}
              key: LANGFUSE_PUBLIC_KEY
        - name: LANGFUSE_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: ${CLIENT_SECRET}
              key: LANGFUSE_SECRET_KEY
      command: ["sh", "-c"]
      args:
        - |
          set -eu
          test -n "\$LANGFUSE_PUBLIC_KEY"
          test -n "\$LANGFUSE_SECRET_KEY"

          echo "Checking Langfuse health..."
          curl -fsS "\$LANGFUSE_HOST/api/public/health" >/dev/null

          echo "Checking authenticated Langfuse Public API..."
          code=\$(curl -sS -o /tmp/projects.json -w "%{http_code}" \
            -u "\$LANGFUSE_PUBLIC_KEY:\$LANGFUSE_SECRET_KEY" \
            "\$LANGFUSE_HOST/api/public/projects")

          if [ "\$code" != "200" ]; then
            echo "LANGFUSE_AUTH_FAILED HTTP \$code"
            cat /tmp/projects.json || true
            exit 1
          fi

          echo "LANGFUSE_AUTH_OK"
YAML

if ! kubectl -n "$APP_NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$POD" --timeout=120s >/dev/null 2>&1; then
  kubectl -n "$APP_NS" logs "$POD" || true
  kubectl -n "$APP_NS" describe pod "$POD" || true
  exit 1
fi

kubectl -n "$APP_NS" logs "$POD"
