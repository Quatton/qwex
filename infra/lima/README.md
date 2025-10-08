# Lima VM + k3s Setup for Cross-Machine Access

This directory contains Lima VM configurations for running k3s clusters that support cross-machine access, replacing the k3d setup.

## Prerequisites

- macOS 13+
- [Homebrew](https://brew.sh)
- Lima (install with `brew install lima`)

No additional networking packages are required—port forwarding exposes the API server on the host.

## Files

- `k3s-server.yaml` - Lima configuration for the k3s server node
- `k3s-agent.yaml` - Lima configuration for k3s agent/worker nodes (optional)
- `setup-kubeconfig.sh` - Script to set up kubectl access from the host

## Quick Start

1. **Start the k3s server:**
   ```bash
   just lima-up
   ```

2. **Set up kubectl access:**
   ```bash
   just lima-kubeconfig
   ```

3. **Install Kueue:**
   ```bash
   just kueue-install
   ```

Or run everything at once:
```bash
just setup-lima
```

## Cross-Machine Access

The VM forwards the k3s API server to port 6443 on the host. Share the host's IP address with
other machines on your network so they can connect to the cluster through that port.

### Accessing from Another Machine

1. Find the host machine's IP:
   ```bash
   ip route get 1 | awk '{print $7}'
   ```

2. From the remote machine, set up kubectl:
   ```bash
   export KUBECONFIG=/path/to/config-roam
   # Update the server URL in the kubeconfig to use the host IP
   kubectl cluster-info
   ```

## Adding Worker Nodes

1. **Start an agent VM:**
   ```bash
   just lima-agent-up
   ```

2. **Get the server token:**
   ```bash
   just lima-secret
   ```

3. **Join the agent to the cluster:**
   ```bash
   just lima-agent-join <TOKEN> <SERVER_IP>
   ```

## Migration from k3d

The Justfile now includes both k3d and lima commands. To migrate:

1. **Stop k3d cluster:**
   ```bash
   just k3d-down
   ```

2. **Start lima cluster:**
   ```bash
   just setup-lima
   ```

3. **Update any scripts that reference k3d-specific configurations**

## Troubleshooting

- **Check VM status:** `just lima-status`
- **Access VM shell:** `just lima-shell`
- **View k3s logs:** `limactl shell roam-server sudo journalctl -u k3s`
- **Restart k3s:** `limactl shell roam-server sudo systemctl restart k3s`

## Networking Details

- **Host port 6443** → VM port 6443 (k3s API)
- **VM networking:** Uses Lima's default user-mode networking
- **Kubeconfig:** Automatically copied to `~/.lima/roam-server/copied-from-guest/kubeconfig.yaml`