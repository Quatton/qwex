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
    go run apps/qwexcloud/main.go run

# Run controller with hot reload
ctrl-watch:
    air

spec:
    # curl -sS http://localhost:3000/openapi-3.0.json -o pkg/client/openapi.json
    go run apps/qwexcloud/main.go spec -o pkg/client/openapi.json --downgrade

# Safe generation: backup old gen.go, generate new one, verify it compiles, then commit
gen: spec
    #!/usr/bin/env bash
    set -euo pipefail
    echo "📦 Backing up existing gen.go..."
    if [ -f pkg/client/gen.go ]; then
        cp pkg/client/gen.go pkg/client/gen.go.bak
    fi
    echo "🔨 Generating new client code..."
    oapi-codegen -generate "client,types" -package client -o pkg/client/gen.go pkg/client/openapi.json
    echo "✅ Verifying generated code compiles..."
    if go build -o /dev/null ./pkg/client/... 2>&1; then
        echo "✅ Generated code is valid!"
        rm -f pkg/client/gen.go.bak
    else
        echo "❌ Generated code has errors! Reverting..."
        if [ -f pkg/client/gen.go.bak ]; then
            mv pkg/client/gen.go.bak pkg/client/gen.go
            echo "⚠️  Reverted to previous gen.go"
        fi
        exit 1
    fi

@ctl *args='':
    go run apps/qwexctl/main.go "$@"

@migrate:
    go run cmds/migrate/main.go