k3d-up:
  k3d cluster create --config infra/k3d/config.yaml

k3d-down:
  k3d cluster delete roam-cluster

k3d-secret:
  docker exec k3d-roam-cluster-server-0 cat /var/lib/rancher/k3s/server/node-token

kueue-install:
  kubectl apply -k infra/kueue
  kubectl wait --for=condition=available --timeout=300s deployment/kueue-controller-manager -n kueue-system

kueue-uninstall:
  kubectl delete -k infra/kueue

setup: k3d-up kueue-install