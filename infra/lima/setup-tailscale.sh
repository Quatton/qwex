#!/bin/bash
set -euo pipefail

echo "=== Tailscale Setup ==="

# Validate required env vars
if [ -z "${K3S_VPN_AUTH_KEY:-}" ]; then
    echo "Error: K3S_VPN_AUTH_KEY not set"
    exit 1
fi

HOSTNAME="${HOSTNAME:-$(hostname)}"

# Check if Tailscale is already installed and connected
if command -v tailscale > /dev/null 2>&1; then
    if tailscale status > /dev/null 2>&1; then
        echo "Tailscale already connected"
        tailscale status
        exit 0
    fi
fi

echo "=== Installing Tailscale ==="
curl -fsSL https://tailscale.com/install.sh | sh

# echo "=== Configuring Firewall ==="
# # Ensure UFW allows K3s ports
# if command -v ufw > /dev/null 2>&1; then
#     ufw --force enable
#     ufw allow 6443/tcp comment "K3s API Server"
#     ufw allow 2379:2380/tcp comment "etcd (HA)"
#     ufw allow 10250/tcp comment "Kubelet metrics"
#     ufw allow 8472/udp comment "Flannel VXLAN"
#     ufw allow 51820/udp comment "Flannel Wireguard IPv4"
#     ufw allow 51821/udp comment "Flannel Wireguard IPv6"
#     ufw allow 5001/tcp comment "Spegel registry"
# fi

echo "=== Connecting to Tailscale ==="
tailscale up \
    --authkey="${K3S_VPN_AUTH_KEY}" \
    --hostname="${HOSTNAME}" \
    --ssh \
    --accept-routes \
    --accept-dns=true

echo "=== Waiting for Tailscale IP ==="
until TAILSCALE_IP=$(tailscale ip -4 2>/dev/null); do
    echo "Waiting for Tailscale IP..."
    sleep 2
done


# Extract hostname: try tailscale status --json then fall back to `tailscale ip -4 --json` or hostname
TAILSCALE_HOSTNAME=""
if command -v jq >/dev/null 2>&1; then
    TAILSCALE_HOSTNAME=$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//') || true
fi
if [[ -z "$TAILSCALE_HOSTNAME" ]]; then
    # Fallback: use the local hostname or tailscale ip output
    TAILSCALE_HOSTNAME=$(tailscale ip -4 2>/dev/null || echo "${HOSTNAME}")
fi

echo "=== Tailscale Connected ==="
echo "  IP: ${TAILSCALE_IP}"
echo "  Hostname: ${TAILSCALE_HOSTNAME}"
echo "  MagicDNS: ${HOSTNAME}"

# Save for reference under /tmp as the Justfile scripts expect
printf "%s" "${TAILSCALE_IP}" > /tmp/tailscale-ip
printf "%s" "${TAILSCALE_HOSTNAME}" > /tmp/tailscale-hostname
chmod 644 /tmp/tailscale-ip /tmp/tailscale-hostname

echo "✓ Tailscale setup complete!"