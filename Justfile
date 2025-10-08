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
lima-up:
  limactl start infra/lima/k3s-server.yaml --name roam-server

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

lima-agent-up:
  limactl start infra/lima/k3s-agent.yaml --name roam-agent

lima-agent-join TOKEN SERVER_IP:
  limactl shell roam-agent "curl -sfL https://get.k3s.io | K3S_URL=https://{{SERVER_IP}}:6443 K3S_TOKEN={{TOKEN}} sh -"

lima-secret:
  limactl shell roam-server sudo cat /var/lib/rancher/k3s/server/node-token

lima-tailscale-install:
  ./infra/lima/install-tailscale.sh roam-server

lima-tailscale-up ARGS="":
  ./infra/lima/tailscale-up.sh roam-server {{ARGS}}

lima-tailscale-status:
  limactl shell roam-server sudo tailscale status

kueue-install:
  kubectl apply --server-side=true --force-conflicts -k infra/kueue
  kubectl wait --for=condition=available --timeout=300s deployment/kueue-controller-manager -n kueue-system

kueue-uninstall:
  kubectl delete -k infra/kueue

# Setup commands for both k3d and lima
setup-k3d: k3d-up kueue-install
setup-lima: lima-up lima-kubeconfig kueue-install