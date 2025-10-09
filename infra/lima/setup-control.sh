#!/bin/bash
set -euo pipefail

echo "=== K3s Control Plane Setup ==="

K3S_SERVER_TAILSCALE_HOST="${K3S_SERVER_TAILSCALE_HOST:-k3s-control}"

# Verify Tailscale is running
if ! tailscale status > /dev/null 2>&1; then
    echo "Error: Tailscale not connected. Run: just tailscale-control"
    exit 1
fi

# Get Tailscale info
TAILSCALE_IP=$(tailscale ip -4)
TAILSCALE_HOSTNAME=$(tailscale status --json | jq -r '.Self.DNSName' | sed 's/\.$//')

echo "Using Tailscale IP: ${TAILSCALE_IP}"
echo "Using Tailscale Hostname: ${TAILSCALE_HOSTNAME}"

# Check if k3s is already installed
if systemctl is-active --quiet k3s; then
    echo "k3s is already running"
    systemctl status k3s --no-pager
    exit 0
fi

echo "=== Installing k3s Control Plane ==="

# Build k3s server args
K3S_ARGS="server \
    --disable traefik \
    --disable servicelb \
    --node-ip=${TAILSCALE_IP} \
    --node-external-ip=${TAILSCALE_IP} \
    --advertise-address=${TAILSCALE_IP} \
    --bind-address=0.0.0.0 \
    --tls-san=${TAILSCALE_IP} \
    --tls-san=${TAILSCALE_HOSTNAME} \
    --tls-san=${K3S_SERVER_TAILSCALE_HOST} \
    --tls-san=localhost \
    --tls-san=127.0.0.1 \
    --flannel-iface=tailscale0 \
    --kube-apiserver-arg=bind-address=0.0.0.0 \
    --kube-apiserver-arg=advertise-address=${TAILSCALE_IP}"

# Conditionally add --token if K3S_TOKEN is set
if [ -n "${K3S_TOKEN:-}" ]; then
    echo "Using pre-shared K3S_TOKEN"
    K3S_ARGS="${K3S_ARGS} --token=${K3S_TOKEN}"
fi

# Install k3s
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="${K3S_ARGS}" sh -

echo "=== Configuring k3s systemd unit ==="
# Ensure k3s starts after Tailscale
mkdir -p /etc/systemd/system/k3s.service.d
cat > /etc/systemd/system/k3s.service.d/tailscale.conf <<EOF
[Unit]
After=tailscaled.service
Requires=tailscaled.service
EOF

systemctl daemon-reload

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
cp /etc/rancher/k3s/k3s.yaml /tmp/k3s.yaml
chmod 644 /tmp/k3s.yaml

# Use MagicDNS hostname in kubeconfig
sed -i "s|https://127.0.0.1:6443|https://${TAILSCALE_HOSTNAME}:6443|g" /tmp/k3s.yaml

# Save token for workers
cp /var/lib/rancher/k3s/server/node-token /tmp/k3s-token
chmod 644 /tmp/k3s-token

echo "=== Control Plane Ready ==="
echo "  Tailscale IP: ${TAILSCALE_IP}"
echo "  MagicDNS: ${TAILSCALE_HOSTNAME}"
echo "  API Server: https://${TAILSCALE_HOSTNAME}:6443"
echo ""
echo "Next steps:"
echo "  just kubeconfig"
echo "  export KUBECONFIG=~/.kube/k3s-config"
echo "  just agent-up k3s-worker-1"