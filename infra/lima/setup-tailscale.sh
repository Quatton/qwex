#!/bin/bash
set -euo pipefail

echo "=== Tailscale Setup ==="

# Validate required env vars
if [ -z "${K3S_VPN_AUTH_KEY:-}" ]; then
    echo "Error: K3S_VPN_AUTH_KEY not set"
    exit 1
fi

HOSTNAME="${HOSTNAME:-$(hostname)}"

echo "=== Installing Tailscale ==="
curl -fsSL https://tailscale.com/install.sh | sh

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

echo "Tailscale Status:"
tailscale status
echo "Your Tailscale IP is: $TAILSCALE_IP"
echo "Your Tailscale Hostname is: $HOSTNAME"