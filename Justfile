# Load dotenv if available
set dotenv-load := true
set positional-arguments

default:
    just --list

# Create k3d cluster with apps directory mounted at /mnt/apps
k3d-create:
    k3d cluster create  --config infra/k3d-config.yaml

# Run controller locally for development
ctrl-dev:
    cd apps/controller && go run main.go

# Run controller with hot reload
ctrl-watch:
    air

spec:
    curl -sS http://localhost:3000/openapi-3.0.json -o pkg/client/openapi.json

gen:
    oapi-codegen -generate "client,types" -package client -o pkg/client/gen.go pkg/client/openapi.json

@ctl *args='':
    go run apps/qwexctl/main.go "$@"

@migrate:
    go run cmd/migrate/main.go