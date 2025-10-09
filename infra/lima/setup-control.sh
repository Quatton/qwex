#!/bin/bash
set -euo pipefail

echo "=== K3s Control Plane Setup ==="

K3S_SERVER_TAILSCALE_HOST="${K3S_SERVER_TAILSCALE_HOST:-k3s-control}"

if [ -z "${K3S_VPN_AUTH_KEY:-}" ]; then
    echo "Error: K3S_VPN_AUTH_KEY not set"
    exit 1
fi

# Verify Tailscale is running (exit if not)
if ! tailscale status > /dev/null 2>&1; then
    echo "Error: Tailscale not connected."
    exit 1
fi

# Get Tailscale info
TAILSCALE_IP=$(tailscale ip -4)
# Try to get MagicDNS hostname, fallback to hostname
TAILSCALE_HOSTNAME=""
if command -v jq >/dev/null 2>&1; then
    TAILSCALE_HOSTNAME=$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//') || true
fi
if [[ -z "$TAILSCALE_HOSTNAME" ]]; then
    TAILSCALE_HOSTNAME=$(hostname)
fi

echo "Using Tailscale IP: ${TAILSCALE_IP}"
echo "Using Tailscale Hostname: ${TAILSCALE_HOSTNAME}"

# Check if k3s is already installed; print status but continue
if systemctl is-active --quiet k3s; then
    echo "k3s appears to be running — printing status"
    systemctl status k3s --no-pager || true
    # continue on; installer will handle re-install or configuration as needed
fi

echo "=== Installing k3s Control Plane ==="

# Build k3s server args safely using an array (avoids backslashes/quoting issues)
K3S_ARG_LIST=(
    server
    --write-kubeconfig-mode=644
    --disable traefik
    --disable servicelb
    --node-ip "${TAILSCALE_IP}"
    --node-external-ip "${TAILSCALE_IP}"
    --advertise-address "${TAILSCALE_IP}"
    --bind-address=0.0.0.0
    --tls-san "${TAILSCALE_IP}"
    --tls-san "${TAILSCALE_HOSTNAME}"
    --tls-san "${K3S_SERVER_TAILSCALE_HOST}"
    --tls-san=localhost
    --tls-san=127.0.0.1
    --flannel-iface=tailscale0
    --kube-apiserver-arg=bind-address=0.0.0.0
    --kube-apiserver-arg="advertise-address=${TAILSCALE_IP}"
    --vpn-auth="name=tailscale,joinKey=${K3S_VPN_AUTH_KEY:-}"
)

# Conditionally add --token if K3S_TOKEN is set (preserve spacing)
if [ -n "${K3S_TOKEN:-}" ]; then
    echo "Using pre-shared K3S_TOKEN"
    K3S_ARG_LIST+=(--token="${K3S_TOKEN}")
fi

# Join list into a single string safe for INSTALL_K3S_EXEC
K3S_ARGS="${K3S_ARG_LIST[*]}"

# Install k3s
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="${K3S_ARGS}" sh -

echo "=== Waiting for k3s API Server ==="

# Wait for API server on localhost
until curl -k https://localhost:6443/livez > /dev/null 2>&1; do
    echo "Waiting for API server on localhost..."
    sleep 3
done

# Wait for kubectl to work
until kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get nodes > /dev/null 2>&1; do
    echo "Waiting for kubectl..."
    sleep 3
done

# Wait for API server on Tailscale IP
until curl -k https://${TAILSCALE_IP}:6443/livez > /dev/null 2>&1; do
    echo "Waiting for API server on Tailscale IP..."
    sleep 3
done

echo "=== Creating Kubeconfig ==="

# Create kubeconfig with MagicDNS hostname
mkdir -p /tmp
cp /etc/rancher/k3s/k3s.yaml /tmp/k3s.yaml
chmod 644 /tmp/k3s.yaml

# Use MagicDNS hostname in kubeconfig (portable sed: create a temp and overwrite)
tmp_kube="/tmp/k3s.yaml.tmp"
sed "s|https://127.0.0.1:6443|https://${TAILSCALE_HOSTNAME}:6443|g" /tmp/k3s.yaml > "$tmp_kube" && mv "$tmp_kube" /tmp/k3s.yaml

# Save token for workers
if [[ -f /var/lib/rancher/k3s/server/node-token ]]; then
    cp /var/lib/rancher/k3s/server/node-token /tmp/k3s-token
    chmod 644 /tmp/k3s-token
fi

echo "=== Control Plane Ready ==="
echo "  Tailscale IP: ${TAILSCALE_IP}"
echo "  MagicDNS: ${TAILSCALE_HOSTNAME}"
echo "  API Server: https://${TAILSCALE_HOSTNAME}:6443"
echo ""
echo "Next steps:"
echo "  just kubeconfig"
echo "  export KUBECONFIG=~/.kube/k3s-config"
echo "  just agent-up k3s-worker-1"