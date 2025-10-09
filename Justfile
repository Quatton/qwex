# Load dotenv if available
set dotenv-load := true

export K3S_VPN_AUTH_KEY := env_var_or_default("K3S_VPN_AUTH_KEY", "")
export K3S_TOKEN := env_var_or_default("K3S_TOKEN", "devtoken")
export K3S_SERVER_TAILSCALE_HOST := env_var_or_default("K3S_SERVER_TAILSCALE_HOST", "k3s-control")


# Default recipe
default:
    @just --list

# ============================================================================
# VM Management
# ============================================================================

# Start control plane VM (minimal, no k3s)
vm-control-up:
    limactl start --name=k3s-control lima-control.yaml

# Start agent VM (minimal, no k3s)
vm-agent-up NAME="k3s-worker":
    limactl start --name={{NAME}} lima-agent.yaml

# Stop VM
vm-stop NAME:
    limactl stop {{NAME}}

# Delete VM
vm-delete NAME:
    limactl delete {{NAME}}

# Shell into VM
vm-shell NAME:
    limactl shell {{NAME}}

# ============================================================================
# Tailscale Setup (one-time per VM)
# ============================================================================

# Setup Tailscale on control plane
tailscale-control:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${K3S_VPN_AUTH_KEY}" ]; then
        echo "Error: K3S_VPN_AUTH_KEY must be set"
        exit 1
    fi
    echo "Setting up Tailscale on control plane..."
    limactl copy setup-tailscale.sh k3s-control:/tmp/
    limactl shell k3s-control sudo K3S_VPN_AUTH_KEY="${K3S_VPN_AUTH_KEY}" HOSTNAME="${K3S_SERVER_TAILSCALE_HOST}" /tmp/setup-tailscale.sh

# Setup Tailscale on agent
tailscale-agent NAME:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${K3S_VPN_AUTH_KEY}" ]; then
        echo "Error: K3S_VPN_AUTH_KEY must be set"
        exit 1
    fi
    WORKER_HOSTNAME="${NAME}"
    echo "Setting up Tailscale on ${WORKER_HOSTNAME}..."
    limactl copy setup-tailscale.sh {{NAME}}:/tmp/
    limactl shell {{NAME}} sudo K3S_VPN_AUTH_KEY="${K3S_VPN_AUTH_KEY}" HOSTNAME="${WORKER_HOSTNAME}" /tmp/setup-tailscale.sh

# ============================================================================
# K3s Management (can restart independently)
# ============================================================================

# Install k3s on control plane
k3s-control-up:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing k3s on control plane..."
    limactl copy setup-k3s-control.sh k3s-control:/tmp/
    limactl shell k3s-control sudo K3S_TOKEN="${K3S_TOKEN}" K3S_SERVER_TAILSCALE_HOST="${K3S_SERVER_TAILSCALE_HOST}" /tmp/setup-k3s-control.sh

# Install k3s on agent
k3s-agent-up NAME:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing k3s agent on {{NAME}}..."
    limactl copy setup-k3s-agent.sh {{NAME}}:/tmp/
    limactl shell {{NAME}} sudo K3S_TOKEN="${K3S_TOKEN}" K3S_SERVER_TAILSCALE_HOST="${K3S_SERVER_TAILSCALE_HOST}" /tmp/setup-k3s-agent.sh

# Restart k3s on control plane
k3s-control-restart:
    limactl shell k3s-control sudo systemctl restart k3s

# Restart k3s on agent
k3s-agent-restart NAME:
    limactl shell {{NAME}} sudo systemctl restart k3s-agent

# Stop k3s on control plane
k3s-control-stop:
    limactl shell k3s-control sudo systemctl stop k3s

# Stop k3s on agent
k3s-agent-stop NAME:
    limactl shell {{NAME}} sudo systemctl stop k3s-agent

# Uninstall k3s from control plane
k3s-control-uninstall:
    -limactl shell k3s-control sudo /usr/local/bin/k3s-uninstall.sh

# Uninstall k3s from agent
k3s-agent-uninstall NAME:
    -limactl shell {{NAME}} sudo /usr/local/bin/k3s-agent-uninstall.sh

# ============================================================================
# Complete Setup Workflows
# ============================================================================

# Full control plane setup (VM + Tailscale + k3s)
control-up: vm-control-up
    @echo "Waiting for VM to be ready..."
    @sleep 10
    @just tailscale-control
    @echo "Waiting for Tailscale..."
    @sleep 5
    @just k3s-control-up
    @echo "✓ Control plane ready!"

# Full agent setup (VM + Tailscale + k3s)
agent-up NAME="k3s-worker": (vm-agent-up NAME)
    @echo "Waiting for VM to be ready..."
    @sleep 10
    @just tailscale-agent {{NAME}}
    @echo "Waiting for Tailscale..."
    @sleep 5
    @just k3s-agent-up {{NAME}}
    @echo "✓ Agent {{NAME}} ready!"

# Full cluster setup (1 control + 2 agents)
cluster-up: control-up
    @just agent-up k3s-worker-1
    @just agent-up k3s-worker-2
    @just kubeconfig
    @echo ""
    @echo "✓ Cluster ready!"
    @just status

# ============================================================================
# Kubeconfig & Status
# ============================================================================

# Get kubeconfig from control plane
kubeconfig:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p ~/.kube
    echo "Fetching kubeconfig from control plane..."
    limactl shell k3s-control sudo cat /tmp/k3s.yaml > ~/.kube/k3s-config
    echo "✓ Kubeconfig saved to ~/.kube/k3s-config"
    echo ""
    echo "Run: export KUBECONFIG=~/.kube/k3s-config"

# Get k3s token from control plane
token:
    @limactl shell k3s-control sudo cat /tmp/k3s-token 2>/dev/null || echo "Token not found - k3s not installed yet?"

# Show cluster status
status:
    @echo "=== Lima VMs ==="
    @limactl list
    @echo ""
    @echo "=== Tailscale Status ==="
    @echo "Control Plane:"
    @limactl shell k3s-control tailscale status --peers=false 2>/dev/null || echo "  Not connected"
    @echo ""
    @echo "=== Kubernetes Nodes ==="
    @kubectl get nodes -o wide 2>/dev/null || echo "Set KUBECONFIG first: export KUBECONFIG=~/.kube/k3s-config"

# ============================================================================
# Kueue
# ============================================================================

# Deploy Kueue
deploy-kueue:
    kubectl apply -k kueue/overlays/production
    kubectl wait --for=condition=available --timeout=300s deployment/kueue-controller-manager -n kueue-system

# ============================================================================
# Cleanup
# ============================================================================

# Clean everything (VMs, k3s, Tailscale)
clean:
    -limactl stop k3s-control
    -limactl delete k3s-control
    -limactl list | grep k3s-worker | awk '{print $1}' | xargs -r -n1 limactl stop
    -limactl list | grep k3s-worker | awk '{print $1}' | xargs -r -n1 limactl delete

# Clean only k3s (keep VMs and Tailscale)
clean-k3s:
    @echo "Uninstalling k3s from all nodes..."
    -just k3s-control-uninstall
    -limactl list | grep k3s-worker | awk '{print $1}' | xargs -r -n1 just k3s-agent-uninstall
