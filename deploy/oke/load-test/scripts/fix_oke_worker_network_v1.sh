#!/usr/bin/env bash
# fix_oke_worker_network_v1.sh
# Run ON EACH OKE WORKER NODE as root or with sudo.
set -Eeuo pipefail

log() { printf '[oke-worker-network] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run this script with sudo/root." >&2
  exit 1
fi

log "Loading br_netfilter..."
modprobe br_netfilter

log "Persisting br_netfilter..."
cat >/etc/modules-load.d/br_netfilter.conf <<'EOF'
br_netfilter
EOF

log "Applying Kubernetes networking sysctls..."
cat >/etc/sysctl.d/99-kubernetes-network.conf <<'EOF'
net.bridge.bridge-nf-call-iptables=1
net.bridge.bridge-nf-call-ip6tables=1
net.ipv4.ip_forward=1
EOF

sysctl --system >/dev/null

log "Validating kernel/module settings..."
lsmod | grep -q '^br_netfilter' || { echo "ERROR: br_netfilter is not loaded." >&2; exit 1; }
[[ "$(sysctl -n net.bridge.bridge-nf-call-iptables)" == "1" ]] || { echo "ERROR: bridge-nf-call-iptables != 1" >&2; exit 1; }
[[ "$(sysctl -n net.ipv4.ip_forward)" == "1" ]] || { echo "ERROR: ip_forward != 1" >&2; exit 1; }

log "Restarting CRI-O and kubelet..."
systemctl restart crio
systemctl restart kubelet

log "Worker network correction completed."
