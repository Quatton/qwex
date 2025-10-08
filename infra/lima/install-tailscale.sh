#!/usr/bin/env bash
# Install Tailscale inside a Lima instance

set -euo pipefail

INSTANCE_NAME="${1:-roam-server}"

echo "Installing Tailscale in instance: ${INSTANCE_NAME}" 

echo "Downloading and installing Tailscale inside the VM..."
limactl shell "${INSTANCE_NAME}" "curl -fsSL https://tailscale.com/install.sh | sudo sh"

echo "Tailscale install script completed. Authenticate with either:"
echo "  TS_AUTHKEY=tskey-xxx just lima-tailscale-up"
echo "or"
echo "  just lima-tailscale-up ARGS=\"--auth-key=tskey-xxx\""