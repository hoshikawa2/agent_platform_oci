#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
ENV="$LT/.env.runtime"
[[ -f "$ENV" ]] || { echo "Run prepare_env.sh first" >&2; exit 1; }
source "$ENV"
NS="${K8S_NAMESPACE:-agent-load-test}"
IMAGE="$(cat "$LT/.backend-image" 2>/dev/null || true)"
[[ -n "$IMAGE" ]] || IMAGE="${OCI_REGION_KEY}.ocir.io/${OCI_TENANCY_NAMESPACE}/${OCIR_REPOSITORY_PREFIX}/agent-template-backend:${IMAGE_TAG}"

"$LT/scripts/sync_langfuse_client_secret.sh"

kubectl -n "$NS" delete pod dependency-check --ignore-not-found >/dev/null 2>&1 || true
cat <<YAML | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: dependency-check
  namespace: $NS
spec:
  restartPolicy: Never
  containers:
    - name: dependency-check
      image: $IMAGE
      envFrom:
        - secretRef:
            name: agent-backend-runtime
      env:
        - name: LANGFUSE_PUBLIC_KEY
          valueFrom:
            secretKeyRef:
              name: langfuse-client
              key: LANGFUSE_PUBLIC_KEY
        - name: LANGFUSE_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: langfuse-client
              key: LANGFUSE_SECRET_KEY
        - name: LANGFUSE_HOST
          valueFrom:
            secretKeyRef:
              name: langfuse-client
              key: LANGFUSE_HOST
      volumeMounts:
        - name: wallet
          mountPath: /app/wallet
          readOnly: true
      command: ["python", "-c"]
      args:
        - |
          import os, json, base64, urllib.request
          import oracledb
          from pymongo import MongoClient

          def ok(name, detail="OK"):
              print(f"{name}: {detail}", flush=True)

          required = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]
          missing = [k for k in required if not os.getenv(k)]
          if missing:
              raise RuntimeError("missing Langfuse variables: " + ", ".join(missing))

          ok("wallet", os.getenv("ADB_WALLET_LOCATION", "<unset>"))
          c = oracledb.connect(
              user=os.environ["ADB_USER"], password=os.environ["ADB_PASSWORD"],
              dsn=os.environ["ADB_DSN"], config_dir=os.environ["ADB_WALLET_LOCATION"],
              wallet_location=os.environ["ADB_WALLET_LOCATION"],
              wallet_password=os.getenv("ADB_WALLET_PASSWORD"),
          )
          ok("oracle", c.version)
          c.close()

          m = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=10000)
          ok("mongo", str(m.admin.command("ping")))
          m.close()

          host = os.environ["LANGFUSE_HOST"].rstrip("/")
          health = urllib.request.urlopen(host + "/api/public/health", timeout=10)
          ok("langfuse_health", str(health.status))

          token = base64.b64encode((os.environ["LANGFUSE_PUBLIC_KEY"] + ":" + os.environ["LANGFUSE_SECRET_KEY"]).encode()).decode()
          req = urllib.request.Request(host + "/api/public/projects", headers={"Authorization": "Basic " + token})
          with urllib.request.urlopen(req, timeout=15) as r:
              body = r.read().decode("utf-8", errors="replace")
              if r.status != 200:
                  raise RuntimeError(f"Langfuse authenticated API returned {r.status}")
              json.loads(body)
              ok("langfuse_authenticated_api", "200")

          ok("dependencies", "ALL_DEPENDENCIES_OK")
  volumes:
    - name: wallet
      secret:
        secretName: agent-backend-wallet
YAML

if ! kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded pod/dependency-check --timeout=180s >/dev/null 2>&1; then
  kubectl -n "$NS" describe pod dependency-check || true
  kubectl -n "$NS" logs dependency-check || true
  exit 1
fi
kubectl -n "$NS" logs dependency-check
