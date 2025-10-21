# Qwex CLI

The user-facing command-line interface for Qwex (Queued Workspace-Aware EXecutor).

## Installation

### From Source

```bash
go install github.com/Quatton/qwex/apps/qwex-cli@latest
```

### Using Homebrew (Coming Soon)

```bash
brew install quatton/tap/qwex
```

## Development

### Build

```bash
go build -o qwex
```

### Run

```bash
./qwex --help
```

### Install Locally

```bash
go install
```

## Usage

### Submit a Batch Job

```bash
qwex batch python train.py
qwex batch -- python main.py --flag value
```

### Check Job Status (Coming Soon)

```bash
qwex status
qwex logs <job-id>
```

## Architecture

This CLI communicates with the Qwex FastAPI controller, which manages Kueue workloads in the Kubernetes cluster.

```
qwex CLI → FastAPI Controller → Kueue → Kubernetes Job
```

## Design Decisions

- **Language**: Go for single binary distribution and easy brew installation
- **Framework**: Cobra for robust CLI command structure
- **Purpose**: User-facing execution and job management
- **Ergonomics**: Left-hand typing optimized name (qwex vs qwexctl for admin tasks)
