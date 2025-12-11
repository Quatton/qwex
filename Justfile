# Load dotenv if available
set dotenv-load := true
set positional-arguments

default:
    just --list

# Create k3d cluster with apps directory mounted at /mnt/apps
k3d-create:
    k3d cluster create -c infra/k3d-config.yaml

clie:
    uv tool install -e apps/qwexcli

clii:
    uv tool install apps/qwexcli --force-reinstall

qwx backend="noop" *args="":
    #!/usr/bin/env bash
    set -euo pipefail

    FILE=".qwex/_internal/compiled/{{ backend }}.sh"
    chmod +x $FILE
    $FILE {{args}}
