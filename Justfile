# Load dotenv if available
set dotenv-load := true
set positional-arguments

default:
    just --list

# Create k3d cluster with apps directory mounted at /mnt/apps
k3d-create:
    k3d cluster create -c infra/k3d-config.yaml