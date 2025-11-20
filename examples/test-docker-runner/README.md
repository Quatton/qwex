# UV Python Project for Docker Runner Testing

This directory contains a sample UV project for testing DockerRunner.

## Structure

```
test-docker-runner/
  qwex.yaml          # qwex configuration
  pyproject.toml     # UV project config
  main.py            # Sample Python script
  README.md          # This file
```

## Usage

```bash
# From project root, run Python script in Docker
just ctl run --config examples/test-docker-runner/qwex.yaml -- python main.py

# Or run arbitrary Python code
just ctl run --config examples/test-docker-runner/qwex.yaml -- python -c "print('Hello from Docker!')"

# List runs
just ctl runs --config examples/test-docker-runner/qwex.yaml
```

## Image

Uses `ghcr.io/astral-sh/uv:python3.12-alpine` for minimal footprint.
