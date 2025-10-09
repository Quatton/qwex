#!/bin/bash
set -euo pipefail

echo "=== K3s Agent Setup ==="

K3S_SERVER_TAILSCALE_HOST="${K3S_SERVER_TAILSCALE_HOST:-k3s-control}"

# Verify Tailscale is running
if ! tailscale status > /dev/null 2>&1; then
    echo "Error: Tailscale not connected. Run: just tailscale-agent "
    exit 1
fi

# Get Tailscale info
TAILSCALE_IP=$(tailscale ip -4)
echo "Worker Tailscale IP: ${TAILSCALE_IP}"

# Check if k3s agent is already installed
if systemctl is-active --quiet k3s-agent; then
    echo "k3s-agent is already running"
    systemctl status k3s-agent --no-pager
    exit 0
fi

echo "=== Resolving Control Plane ==="

# Wait for MagicDNS to resolve control plane
until CONTROL_PLANE_IP=$(tailscale ip -4 ${K3S_SERVER_TAILSCALE_HOST} 2>/dev/null); do
    echo "Waiting for control plane ${K3S_SERVER_TAILSCALE_HOST} to be reachable..."
    sleep 5
done

echo "Control Plane IP: ${CONTROL_PLANE_IP}"

# Wait for control plane API to be ready
echo "Waiting for control plane API server..."
until curl -k https://${CONTROL_PLANE_IP}:6443/livez > /dev/null 2>&1; do
    echo "Control plane API not ready yet..."
    sleep 5
done

echo "=== Getting k3s Token ==="

# Get token - try pre-shared first, then SSH fallback
if [ -n "${K3S_TOKEN:-}" ]; then
    echo "Using pre-shared K3S_TOKEN"
    K3S_JOIN_TOKEN="${K3S_TOKEN}"
else
    echo "Fetching token from control plane via SSH..."
    until K3S_JOIN_TOKEN=$(tailscale ssh ${K3S_SERVER_TAILSCALE_HOST} sudo cat /var/lib/rancher/k3s/server/node-token 2>/dev/null); do
        echo "Waiting to fetch token from control plane..."
        echo "Hint: Set K3S_TOKEN env var or enable Tailscale SSH"
        sleep 10
    done
fi

echo "=== Installing k3s Agent ==="

curl -sfL https://get.k3s.io | \
    K3S_URL="https://${CONTROL_PLANE_IP}:6443" \
    K3S_TOKEN="${K3S_JOIN_TOKEN}" \
    INSTALL_K3S_EXEC="agent \
        --node-ip=${TAILSCALE_IP} \
        --node-external-ip=${TAILSCALE_IP} \
        --flannel-iface=tailscale0" sh -

echo "=== Configuring k3s-agent systemd unit ==="
# Ensure k3s-agent starts after Tailscale
mkdir -p /etc/systemd/system/k3s-agent.service.d
cat > /etc/systemd/system/k3s-agent.service.d/tailscale.conf <<EOF
[Unit]
After=tailscaled.service
Requires=tailscaled.service
EOF

systemctl daemon-reload

echo "=== Agent Setup Complete ==="
echo "  Worker IP: ${TAILSCALE_IP}"
echo "  Connected to: ${CONTROL_PLANE_IP}"
echo ""
echo "Check with: kubectl get nodes"