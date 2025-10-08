#!/usr/bin/env bash
# Helper script to set up kubeconfig for external access to lima k3s cluster

set -euo pipefail

LIMA_INSTANCE_NAME="${1:-roam-server}"
LOCAL_KUBECONFIG="${2:-$HOME/.kube/config-roam}"

echo "Setting up kubeconfig for lima k3s cluster..."

# Get the lima instance directory
LIMA_DIR=$(limactl list "$LIMA_INSTANCE_NAME" --format '{{.Dir}}')

if [[ -z "$LIMA_DIR" ]]; then
    echo "Error: Could not find lima instance '$LIMA_INSTANCE_NAME'"
    exit 1
fi

KUBECONFIG_PATH="$LIMA_DIR/copied-from-guest/kubeconfig.yaml"

if [[ ! -f "$KUBECONFIG_PATH" ]]; then
    echo "Error: Kubeconfig not found at $KUBECONFIG_PATH"
    echo "Make sure the lima VM is running and k3s is installed"
    exit 1
fi

# Copy kubeconfig to local location
cp "$KUBECONFIG_PATH" "$LOCAL_KUBECONFIG"

echo "Kubeconfig saved to: $LOCAL_KUBECONFIG"
echo "To use this config:"
echo "  export KUBECONFIG=$LOCAL_KUBECONFIG"
echo "  kubectl cluster-info"

# Test connectivity
echo "Testing connectivity..."
if KUBECONFIG="$LOCAL_KUBECONFIG" kubectl cluster-info >/dev/null 2>&1; then
    echo "✓ Successfully connected to k3s cluster"
else
    echo "✗ Failed to connect to k3s cluster"
    echo "Make sure the lima VM is running and k3s is installed"
    exit 1
fi