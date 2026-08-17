#!/usr/bin/env bash
# deploy_langfuse_v11.sh
# OKE-safe Langfuse deployment with DNS preflight.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LT="$ROOT/deploy/oke/load-test"
MANIFEST="$LT/langfuse/langfuse-k8s.yaml"
LF_ENV="$LT/.env.langfuse"

NS="${LANGFUSE_NAMESPACE:-langfuse}"
SECRET="langfuse-runtime"
DNS_TEST_NS="${DNS_TEST_NAMESPACE:-default}"

PG_FQDN="postgres.${NS}.svc.cluster.local"
REDIS_FQDN="redis.${NS}.svc.cluster.local"
CH_FQDN="clickhouse.${NS}.svc.cluster.local"
MINIO_FQDN="minio.${NS}.svc.cluster.local"
MONGO_FQDN="mongo.${NS}.svc.cluster.local"

log() { printf '[langfuse-deploy] %s\n' "$*"; }
die() { printf '[langfuse-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup_probe() {
  local ns="${1:-$DNS_TEST_NS}"
  local name="${2:-}"
  [[ -n "$name" ]] && kubectl -n "$ns" delete pod "$name" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}

trap 'rc=$?; if (( rc != 0 )); then
  echo >&2
  echo "[langfuse-deploy] Failure detected." >&2
  kubectl get nodes -o wide 2>/dev/null >&2 || true
  kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide 2>/dev/null >&2 || true
  kubectl -n "$NS" get pods,svc,pvc 2>/dev/null >&2 || true
fi
exit $rc' EXIT

command -v kubectl >/dev/null 2>&1 || die "kubectl not found in PATH"
[[ -f "$MANIFEST" ]] || die "manifest not found: $MANIFEST"

log "Checking Kubernetes API..."
kubectl version --request-timeout=15s >/dev/null || die "cannot reach Kubernetes API"

log "Checking worker nodes..."
not_ready="$(kubectl get nodes --no-headers 2>/dev/null | awk '$2 != "Ready" {print $1 ":" $2}')"
[[ -z "$not_ready" ]] || { printf '%s\n' "$not_ready" >&2; die "one or more OKE nodes are not Ready"; }

log "Checking CoreDNS..."
kubectl -n kube-system get svc kube-dns >/dev/null 2>&1 || die "kube-dns Service not found"
dns_ready="$(kubectl -n kube-system get pods -l k8s-app=kube-dns --no-headers 2>/dev/null | awk '$2 ~ /^[0-9]+\/[0-9]+$/ {split($2,a,"/"); if(a[1]==a[2]) n++} END{print n+0}')"
(( dns_ready > 0 )) || die "no Ready CoreDNS pod found"

DNS_IP="$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')"
[[ -n "$DNS_IP" ]] || die "kube-dns ClusterIP is empty"
log "kube-dns ClusterIP: $DNS_IP"

probe="oke-dns-preflight-$(date +%s)"
log "Running DNS preflight BEFORE Langfuse deployment..."
kubectl -n "$DNS_TEST_NS" run "$probe"   --restart=Never   --image=docker.io/library/busybox:1.36   --command -- sh -c   "echo '--- /etc/resolv.conf ---';
   cat /etc/resolv.conf;
   echo '--- default resolver ---';
   nslookup kubernetes.default.svc.cluster.local;
   echo '--- direct kube-dns ---';
   nslookup kubernetes.default.svc.cluster.local ${DNS_IP}" >/dev/null

if ! kubectl -n "$DNS_TEST_NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$probe" --timeout=90s >/dev/null 2>&1; then
  echo >&2
  echo "================ DNS PREFLIGHT FAILED ================" >&2
  kubectl -n "$DNS_TEST_NS" logs "$probe" >&2 || true
  kubectl -n "$DNS_TEST_NS" describe pod "$probe" >&2 || true
  cleanup_probe "$DNS_TEST_NS" "$probe"
  die "cluster DNS is unavailable; fix worker/CNI networking before deploying Langfuse"
fi
kubectl -n "$DNS_TEST_NS" logs "$probe" || true
cleanup_probe "$DNS_TEST_NS" "$probe"
log "Cluster DNS preflight PASSED."

log "Generating Langfuse runtime environment..."
"$LT/scripts/prepare_env.sh"
[[ -s "$LF_ENV" ]] || die "Langfuse env was not generated: $LF_ENV"

required_keys=(
  LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY
  LANGFUSE_INIT_PROJECT_PUBLIC_KEY LANGFUSE_INIT_PROJECT_SECRET_KEY
  LANGFUSE_INIT_ORG_ID LANGFUSE_INIT_ORG_NAME
  LANGFUSE_INIT_PROJECT_ID LANGFUSE_INIT_PROJECT_NAME
  LANGFUSE_INIT_USER_EMAIL LANGFUSE_INIT_USER_NAME
  LANGFUSE_INIT_USER_PASSWORD LANGFUSE_NEXTAUTH_SECRET
  LANGFUSE_SALT LANGFUSE_ENCRYPTION_KEY
  LANGFUSE_POSTGRES_PASSWORD LANGFUSE_REDIS_PASSWORD
  LANGFUSE_CLICKHOUSE_PASSWORD LANGFUSE_MINIO_PASSWORD
)

for key in "${required_keys[@]}"; do
  grep -qE "^${key}=.+" "$LF_ENV" || die "required key '$key' missing/empty in $LF_ENV"
done

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

pg_password="$(grep '^LANGFUSE_POSTGRES_PASSWORD=' "$LF_ENV" | cut -d= -f2-)"
[[ -n "$pg_password" ]] || die "LANGFUSE_POSTGRES_PASSWORD is empty"
db_url="postgresql://postgres:${pg_password}@${PG_FQDN}:5432/postgres"

tmp_env="$(mktemp)"
grep -vE '^(DATABASE_URL|DIRECT_URL)=' "$LF_ENV" > "$tmp_env"
printf 'DATABASE_URL=%s\n' "$db_url" >> "$tmp_env"
printf 'DIRECT_URL=%s\n' "$db_url" >> "$tmp_env"

log "Creating/updating Secret/$SECRET..."
kubectl -n "$NS" create secret generic "$SECRET"   --from-env-file="$tmp_env"   --dry-run=client -o yaml | kubectl apply -f - >/dev/null
rm -f "$tmp_env"

log "Applying Langfuse manifest..."
kubectl apply -f "$MANIFEST"

for dep in mongo postgres redis clickhouse minio langfuse-worker langfuse-web; do
  kubectl -n "$NS" get deployment "$dep" >/dev/null 2>&1 || die "deployment/$dep is missing"
done

pgdata="$(kubectl -n "$NS" get deployment postgres -o jsonpath='{.spec.template.spec.containers[?(@.name=="postgres")].env[?(@.name=="PGDATA")].value}')"
[[ "$pgdata" == "/var/lib/postgresql/data/pgdata" ]] || die "Postgres PGDATA is incorrect: '$pgdata'"

log "Scaling web/worker to zero until infrastructure is healthy..."
kubectl -n "$NS" scale deployment/langfuse-web --replicas=0 >/dev/null
kubectl -n "$NS" scale deployment/langfuse-worker --replicas=0 >/dev/null

for dep in mongo postgres redis clickhouse minio; do
  log "Waiting for deployment/$dep ..."
  kubectl -n "$NS" rollout status "deployment/$dep" --timeout=10m
done

log "Checking service endpoints..."
for svc in mongo postgres redis clickhouse minio; do
  ip="$(kubectl -n "$NS" get endpoints "$svc" -o jsonpath='{.subsets[0].addresses[0].ip}' 2>/dev/null || true)"
  [[ -n "$ip" ]] || die "service/$svc has no ready endpoint"
  log "$svc endpoint: $ip"
done

probe="langfuse-infra-probe-$(date +%s)"
log "Running Langfuse infrastructure DNS/TCP probe..."
kubectl -n "$NS" run "$probe"   --restart=Never   --image=docker.io/library/busybox:1.36   --command -- sh -c   "set -e;
   nslookup ${PG_FQDN};
   nslookup ${REDIS_FQDN};
   nslookup ${CH_FQDN};
   nslookup ${MINIO_FQDN};
   nslookup ${MONGO_FQDN};
   nc -zvw5 ${PG_FQDN} 5432;
   nc -zvw5 ${REDIS_FQDN} 6379;
   nc -zvw5 ${CH_FQDN} 8123;
   nc -zvw5 ${MINIO_FQDN} 9000;
   nc -zvw5 ${MONGO_FQDN} 27017;
   echo 'ALL LANGFUSE INFRA CHECKS PASSED'" >/dev/null

if ! kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$probe" --timeout=120s >/dev/null 2>&1; then
  kubectl -n "$NS" logs "$probe" >&2 || true
  kubectl -n "$NS" describe pod "$probe" >&2 || true
  cleanup_probe "$NS" "$probe"
  die "Langfuse infrastructure probe failed; web/worker remain scaled to zero"
fi
kubectl -n "$NS" logs "$probe" || true
cleanup_probe "$NS" "$probe"

log "Infrastructure healthy. Applying Langfuse web/worker memory sizing..."
kubectl -n "$NS" set resources deployment/langfuse-worker --requests=cpu=500m,memory=2Gi --limits=cpu=2,memory=4Gi >/dev/null
kubectl -n "$NS" set resources deployment/langfuse-web --requests=cpu=500m,memory=2Gi --limits=cpu=2,memory=4Gi >/dev/null
kubectl -n "$NS" set env deployment/langfuse-worker NODE_OPTIONS=--max-old-space-size=3072 >/dev/null
kubectl -n "$NS" set env deployment/langfuse-web NODE_OPTIONS=--max-old-space-size=3072 HOSTNAME=0.0.0.0 >/dev/null

log "Scaling worker/web to 1..."
kubectl -n "$NS" scale deployment/langfuse-worker --replicas=1 >/dev/null
kubectl -n "$NS" scale deployment/langfuse-web --replicas=1 >/dev/null

kubectl -n "$NS" rollout status deployment/langfuse-worker --timeout=15m
kubectl -n "$NS" rollout status deployment/langfuse-web --timeout=15m

log "Verifying Secret/$SECRET before synchronization..."
kubectl -n "$NS" get secret "$SECRET" >/dev/null || die "Secret/$SECRET became unavailable in namespace $NS"

APP_NS="$(sed -n -E 's/^K8S_NAMESPACE=(.*)$/\1/p' "$LT/.env.runtime" | tail -n 1 | tr -d '\r' | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
APP_NS="${APP_NS:-agent-load-test}"

log "Synchronizing Langfuse project keys to backend namespace $APP_NS..."
LANGFUSE_NAMESPACE="$NS" K8S_NAMESPACE="$APP_NS" \
  "$LT/scripts/sync_langfuse_client_secret.sh"

log "Validating Langfuse health and authenticated Public API..."
"$LT/scripts/validate_langfuse_integration.sh"

log "Final state:"
kubectl -n "$NS" get pods,svc,pvc -o wide
printf '\nUI: kubectl -n %s port-forward --address 127.0.0.1 svc/langfuse-web 3005:3000\n' "$NS"
log "Langfuse deployment completed successfully."
