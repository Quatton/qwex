# Load dotenv if available
set dotenv-load := true

default:
    just --list

# Create k3d cluster with apps directory mounted at /mnt/apps
k3d-create:
    k3d cluster create  --config infra/k3d-config.yaml