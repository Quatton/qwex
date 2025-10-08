#!/usr/bin/env bash
# Run `tailscale up` inside a Lima VM with optional auth key handling.

set -euo pipefail

INSTANCE_NAME="${1:-roam-server}"
shift || true

# Additional flags passed via CLI
USER_FLAGS=("$@")

CMD=("sudo" "tailscale" "up")

if [[ -n "${TS_AUTHKEY:-}" ]]; then
  CMD+=("--auth-key=${TS_AUTHKEY}")
fi

if [[ ${#USER_FLAGS[@]} -gt 0 ]]; then
  CMD+=("${USER_FLAGS[@]}")
fi

echo "Running inside ${INSTANCE_NAME}: ${CMD[*]}"

limactl shell "${INSTANCE_NAME}" "${CMD[@]}"