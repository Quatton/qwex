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

### Join from Another Machine (Same Network)

1. Copy the kubeconfig to the host (already done by `just lima-kubeconfig`).
2. Copy `~/.kube/config-roam` to the remote machine.
3. Edit the copied kubeconfig so the `server` field points to the host's LAN IP, e.g.
   `https://192.168.1.10:6443`.
4. On the remote machine:
   ```bash
   export KUBECONFIG=/path/to/config-roam
   kubectl cluster-info
   ```

### Join via Tailscale

If machines are on different networks, you can run Tailscale inside the Lima VM and on the remote
machine:

1. Install Tailscale inside the VM:
   ```bash
   just lima-tailscale-install
   ```

2. Authenticate Tailscale (opens an auth URL or use an auth key):
    ```bash
    just lima-tailscale-up
    ```
    - Provide an auth key either by setting an environment variable (`TS_AUTHKEY=tskey-123 just 
       lima-tailscale-up`) or by passing flags (`ARGS="--auth-key=tskey-123 --hostname=roam-k3s"`).
    - The command runs interactively; follow the on-screen instructions (or use an auth key) to
       complete login.

3. Retrieve the VM's Tailscale IP:
   ```bash
   just lima-tailscale-status
   # or to get the raw IPs:
   just lima-shell
   tailscale ip -4
   exit
   ```

4. Generate a kubeconfig that targets the Tailscale IP:
   ```bash
   just lima-kubeconfig-tailscale <tailscale-ip>
   ```

5. Share the kubeconfig with other machines on the tailnet. On each remote machine:
   ```bash
   export KUBECONFIG=/path/to/config-roam
   kubectl cluster-info
   ```

Make sure the remote machine is also connected to the same tailnet (install the Tailscale client
and run `tailscale up`).

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
- **VM networking:** Uses Lima's default user-mode networking; optional Tailscale interface if
   enabled
- **Kubeconfig:** Automatically copied to `~/.lima/roam-server/copied-from-guest/kubeconfig.yaml`