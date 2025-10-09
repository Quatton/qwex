# Load dotenv if available
set dotenv-load := true

default:
    just --list

vm-control-up:
    limactl start --name=k3s-control infra/lima/control.yaml

vm-agent-up:
    limactl start --name=k3s-agent infra/lima/agent.yaml

vm-control-down:
    limactl stop k3s-control || true
    limactl delete k3s-control || true

vm-agent-down:
    limactl stop k3s-agent || true
    limactl delete k3s-agent || true

tailscale NAME:
    limactl copy ./infra/lima/setup-tailscale.sh {{NAME}}:~/setup-tailscale.sh
    limactl shell {{NAME}} -- bash -c "chmod +x ~/setup-tailscale.sh && sudo K3S_VPN_AUTH_KEY=$K3S_VPN_AUTH_KEY ~/setup-tailscale.sh && rm ~/setup-tailscale.sh"

k3sup-server TAILSCALE_HOST:
    TAILSCALE_ADDR=$(tailscale ip --4 {{TAILSCALE_HOST}} 2>/dev/null) && \
    [ -n "$TAILSCALE_ADDR" ] || (echo "Error: Could not get Tailscale IP for host {{TAILSCALE_HOST}}" >&2; exit 1) && \
    k3sup install \
    --ip $TAILSCALE_ADDR \
    --user root \
    --k3s-extra-args "--flannel-iface tailscale0 \
        --advertise-address $TAILSCALE_ADDR \
        --node-ip $TAILSCALE_ADDR \
        --node-external-ip $TAILSCALE_ADDR" \
    --k3s-channel latest \
    --context rpis \
    --local-path $HOME/.kube/config \
    --merge

k3sup-agent TAILSCALE_HOST SERVER_HOST:
    TAILSCALE_ADDR=$(tailscale ip --4 {{TAILSCALE_HOST}} 2>/dev/null) && \
    [ -n "$TAILSCALE_ADDR" ] || (echo "Error: Could not get Tailscale IP for host {{TAILSCALE_HOST}}" >&2; exit 1) && \
    SERVER_ADDR=$(tailscale ip --4 {{SERVER_HOST}} 2>/dev/null) && \
    [ -n "$SERVER_ADDR" ] || (echo "Error: Could not get Tailscale IP for server host {{SERVER_HOST}}" >&2; exit 1) && \
    echo "Joining server at $SERVER_ADDR" && \
    echo "Using node IP $TAILSCALE_ADDR" && \
    k3sup join \
    --ip $TAILSCALE_ADDR \
    --user root \
    --server-ip $SERVER_ADDR \
    --k3s-extra-args "--flannel-iface tailscale0 \
        --node-ip $TAILSCALE_ADDR \
        --node-external-ip $TAILSCALE_ADDR" \
    --k3s-channel latest

clean: vm-control-down vm-agent-down

# KUEUE

