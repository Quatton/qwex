set dotenv-load := true

k3d-up:
  k3d cluster create --config infra/k3d/config.yaml

k3d-down:
  k3d cluster delete roam-cluster

k3d-secret:
  docker exec k3d-roam-cluster-server-0 cat /var/lib/rancher/k3s/server/node-token

k3d-status:
  k3d cluster list

k3d-pods:
  kubectl get pods -n=kueue-system

# Lima VM commands for cross-machine k3s setup
# Required env vars (loaded from .env or exported):
#   K3S_VPN_AUTH_KEY   - tailscale auth key used by all nodes
#   K3S_TOKEN          - optional shared cluster token
# Params are set via --set automatically.
# Start the control-plane VM (requires K3S_VPN_AUTH_KEY, optional K3S_TOKEN)
lima-up: 
  envsubst '$K3S_VPN_AUTH_KEY,$K3S_TOKEN' < infra/lima/k3s-server.yaml | limactl start --name roam-server -

lima-down:
  limactl stop -f roam-server
  limactl delete roam-server

lima-status:
  limactl list

lima-shell:
  limactl shell roam-server

lima-kubeconfig:
  ./infra/lima/setup-kubeconfig.sh roam-server

lima-kubeconfig-tailscale HOST:
  ./infra/lima/setup-kubeconfig.sh roam-server $HOME/.kube/config-roam {{HOST}}

# Additional env for agents:
#   K3S_SERVER_TAILSCALE_IP - tailscale IPv4 or hostname of the server node
# Start a worker VM (requires K3S_VPN_AUTH_KEY, K3S_TOKEN, K3S_SERVER_TAILSCALE_IP)
lima-agent-up:
  envsubst '$K3S_VPN_AUTH_KEY,$K3S_TOKEN,$K3S_SERVER_TAILSCALE_IP' < infra/lima/k3s-agent.yaml | limactl start --name roam-agent -
  
lima-secret:
  limactl shell roam-server sudo cat /var/lib/rancher/k3s/server/node-token

lima-agent-down:
  limactl stop -f roam-agent
  limactl delete roam-agent

kueue-install:
  kubectl apply --server-side=true --force-conflicts -k infra/kueue
  kubectl wait --for=condition=available --timeout=300s deployment/kueue-controller-manager -n kueue-system

kueue-uninstall:
  kubectl delete -k infra/kueue

# Setup commands for both k3d and lima
setup-k3d: k3d-up kueue-install
setup-lima: lima-up lima-kubeconfig kueue-install