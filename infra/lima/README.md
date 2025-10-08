# Lima VM + k3s Setup for Cross-Machin   The repo's `.gitignore` already excludes `.env`. `just` is configured with `dotenv-load`, so the
   variables you store in `.env` are available to every recipe. Prefer a proper secrets manager for
   multi-user environments (e.g. `direnv + 1password`, `doppler run -- just lima-up`, etc.).

   Lima uses `param` to inject these values into the VM configuration without exposing them as
   environment variables inside the guest.ccess

This directory contains Lima VM configurations for running k3s clusters that support cross-machine access, replacing the k3d setup.

## Prerequisites

- macOS 13+
- [Homebrew](https://brew.sh)
- Lima (`brew install lima`)
- A Tailscale account and an auth key with subnet auto-approvers configured for the cluster
  podCIDR(s) (default `10.42.0.0/16`, plus IPv6 if you enable dual-stack)

## Files

- `k3s-server.yaml` - Lima configuration for the k3s server node
- `k3s-agent.yaml` - Lima configuration for k3s agent/worker nodes (optional)
- `setup-kubeconfig.sh` - Script to set up kubectl access from the host
- `install-tailscale.sh`, `tailscale-up.sh` - Optional helpers for manual debugging

## Quick Start

The provisioning scripts now use the built-in `--vpn-auth` integration in k3s (available in
v1.27.3+, v1.26.6+, v1.25.11+). Every node uses Tailscale to join a secure mesh; no manual
`tailscale up` or kubeconfig rewrites are required beyond specifying the Tailscale endpoint.

1. **Populate your environment (happens automatically for every `just` run):**

   ```bash
   cp .env.example .env    # then edit .env with your favourite editor
   ```

   Fill in:

   - `K3S_VPN_AUTH_KEY` (required) – a valid reusable Tailscale auth key that is allowed to
     advertise your cluster podCIDR routes.
   - `K3S_TOKEN` (optional) – set if you prefer a pre-defined cluster token; otherwise the server
     will generate one.

   The repo’s `.gitignore` already excludes `.env`. `just` is configured with `dotenv-load`, so the
   variables you store in `.env` are available to every recipe. Prefer a proper secrets manager for
   multi-user environments (e.g. `direnv + 1password`, `doppler run -- just lima-up`, etc.).

2. **Start the control-plane VM:**

   ```bash
   just lima-up
   ```

   The VM installs tailscale, authenticates with the provided key, and launches k3s with
   `--vpn-auth="name=tailscale,joinKey=..."` while advertising its Tailscale IP.

   > Approve the new Tailscale node and advertised routes in the admin console if auto-approvers
   > are not already configured.

3. **Grab the server's Tailscale IP or hostname:**

   ```bash
   just lima-shell
   tailscale ip -4   # or `tailscale status --json`
   exit
   ```

   Export it for later (if you use `fish`, replace `export` with `set -x`):

   ```bash
   export K3S_SERVER_TAILSCALE_IP=100.x.y.z
   ```

   You can also persist it in `.env` (especially if you rely on MagicDNS hostnames) so future
   `just` runs pick it up automatically.

4. **Start one or more worker VMs (each needs the same env vars plus the server address):**

   If you didn't pre-set `K3S_TOKEN` in step 1, fetch the auto-generated token first:

   ```bash
   just lima-secret
   export K3S_TOKEN=<value from output>
   ```

   ```bash
   export K3S_VPN_AUTH_KEY=tskey-123...
   export K3S_TOKEN=super-secret-token          # must match the server token if you set one
   export K3S_SERVER_TAILSCALE_IP=100.x.y.z     # from step 3
   just lima-agent-up
   ```

   The agent provisions tailscale, connects with the same key, and runs
   `k3s agent --vpn-auth="name=tailscale,joinKey=..." --server=https://<server>:6443` with its
   Tailscale IP set for both `--node-ip` and `--node-external-ip`.

   > Approve each worker node (and its subnet routes) in the Tailscale admin console if prompted.

5. **Set up kubectl on the host (uses the copied kubeconfig and rewrites the server endpoint if
   needed):**

   ```bash
   just lima-kubeconfig                       # copies ~/.lima/roam-server/... into ~/.kube/config-roam
   just lima-kubeconfig-tailscale $K3S_SERVER_TAILSCALE_IP   # optional, accepts IP or hostname
   export KUBECONFIG=~/.kube/config-roam
   kubectl get nodes
   ```

6. **Install add-ons (e.g. Kueue) once the cluster is ready:**

   ```bash
   just kueue-install
   ```

## Managing secrets & environment variables

- The easiest local workflow is a `.env` file loaded by `just`. Keep it out of source control (it
   already is) and protect it with filesystem permissions or disk encryption.
- For team usage, lean on a secrets manager. Examples: `op run -- just lima-up`, `doppler run`, or
   `aws-vault exec -- just lima-up`. Each injects the required env vars at invocation time without
   persisting them on disk.
- Fish shell users can export ad-hoc overrides with `set -x VAR value`. Bash/zsh users can use
   `export VAR=value` or prefix a command with `VAR=value just lima-up`.
- Sensitive values like `K3S_VPN_AUTH_KEY` expire or can be revoked; if provisioning fails with the
   error surfaced above, generate a fresh key before retrying.

## Cross-Machine Access

All nodes, including the host, should join the same tailnet. The API server listens on the
server VM's Tailscale interface (`--node-external-ip`), so any machine inside the tailnet can use
the kubeconfig generated above without further tunnel setup.

If you prefer to operate outside Tailscale (e.g. same LAN, testing), you can still use the
forwarded host port 6443 by pointing the kubeconfig `server:` to your host's IP. However, the
recommended path is to use Tailscale everywhere so that nodes, the host, and remote operators all
share the same overlay network.

## Adding Worker Nodes

Follow the quick start steps above for each additional node. Every agent requires the same
`K3S_VPN_AUTH_KEY` and `K3S_TOKEN` (if you set one for the server), plus the server's Tailscale
endpoint. Once provisioned, confirm membership with `kubectl get nodes`.

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
- **Inspect Tailscale:** `just lima-tailscale-status` (or `tailscale status --json` inside the VM)

## Networking Details

- **Host port 6443** → VM port 6443 (k3s API)
- **VM networking:** Uses Lima's default user-mode networking plus the Tailscale interface (k3s
   advertises the Tailscale IPs by default)
- **Kubeconfig:** Automatically copied to `~/.lima/roam-server/copied-from-guest/kubeconfig.yaml`