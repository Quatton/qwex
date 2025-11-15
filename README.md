# QWEX - Queue-based Workload EXecution

A distributed job execution platform built on Kubernetes and Kueue, designed for running workloads across multiple machines with seamless cross-machine networking via Tailscale.

## 🏗️ Architecture Overview

### Flexible Deployment Options

**External Controller (Development & Multi-cluster)**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CLI Client    │───▶│   FastAPI       │───▶│   K3s Cluster   │
│                 │    │   Controller    │    │   + Kueue       │
│   Dev Machine   │    │   (External)    │    │   (Lima VM)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                        │                        │
    Generated                 Kubeconfig              Job Queue
    from OpenAPI            or ServiceAccount         Management
```

**In-Cluster Controller (Production)**
```
┌─────────────────┐         ┌─────────────────────────────────┐
│   CLI Client    │────────▶│          K3s Cluster            │
│                 │         │  ┌─────────────┐ ┌─────────────┐ │
└─────────────────┘         │  │ Controller  │─│   Kueue     │ │
        │                   │  │    Pod      │ │             │ │
    Generated               │  └─────────────┘ └─────────────┘ │
    from OpenAPI            └─────────────────────────────────┘
```

## 📋 Feature Status

### ✅ **Implemented Features**

#### Infrastructure
- [x] **Lima VM Setup** - Cross-machine k3s cluster with Tailscale networking
- [x] **K3s Cluster** - Multi-node cluster (1 control + 2 workers)
- [x] **Kueue Installation** - Job queue management with ClusterQueue and LocalQueue
- [x] **Tailscale Integration** - Secure mesh networking between nodes
- [x] **Basic Job Examples** - Sample Python jobs with resource requests

#### Development Tools
- [x] **Justfile Automation** - VM management and cluster operations
- [x] **UV Package Management** - Fast Python dependency resolution
- [x] **Project Structure** - Monorepo with apps/, infra/, packages/

### 🚧 **In Progress**

#### Job API
- [ ] **FastAPI Controller** - RESTful API for job submission and management
  - [ ] Job submission endpoint (`POST /jobs`)
  - [ ] Job status tracking (`GET /jobs/{id}`)
  - [ ] Job cancellation (`DELETE /jobs/{id}`)
  - [ ] Job logs streaming (`GET /jobs/{id}/logs`)
- [ ] **Kubernetes Integration** - Direct integration with Kueue APIs
- [ ] **Pydantic Models** - Type-safe job specifications and responses

### 📅 **Planned Features**

#### Core API Features
- [ ] **Job Templates** - Predefined job configurations
- [ ] **Batch Job Submission** - Submit multiple jobs at once
- [ ] **Job Dependencies** - DAG-based job execution
- [ ] **Resource Quotas** - Per-user/project resource limits
- [ ] **Job Scheduling** - Cron-based recurring jobs

#### CLI Client
- [ ] **Auto-generated CLI** - From OpenAPI specification
- [ ] **Job Management Commands**
  - [ ] `qwex submit <job-spec>`
  - [ ] `qwex status <job-id>`
  - [ ] `qwex logs <job-id> --follow`
  - [ ] `qwex cancel <job-id>`
  - [ ] `qwex list --user=me --status=running`
- [ ] **Interactive Mode** - REPL for job management
- [ ] **Configuration Management** - API endpoint configuration

#### SDK & Client Libraries
- [ ] **Python Client** - Generated from OpenAPI spec
- [ ] **Go Client** - For integration with other tools
- [ ] **TypeScript Client** - Web dashboard support

#### Advanced Features
- [ ] **Web Dashboard** - React-based UI for job management
- [ ] **Authentication & Authorization** - RBAC integration with Kubernetes
- [ ] **Metrics & Monitoring** - Prometheus metrics and Grafana dashboards
- [ ] **Job Artifacts** - S3-compatible storage for job outputs
- [ ] **Multi-cluster Support** - Submit jobs across different clusters
- [ ] **GPU Support** - NVIDIA GPU resource scheduling
- [ ] **Spot Instance Integration** - Cost optimization with preemptible nodes

#### Developer Experience
- [ ] **Hot Reload Development** - Live code updates in Lima VMs
- [ ] **Integration Tests** - End-to-end testing with real cluster
- [ ] **Performance Benchmarks** - Job throughput and latency metrics
- [ ] **Documentation Site** - Comprehensive API and usage docs

## 🚀 **Quick Start**

### Prerequisites
- macOS 13+
- [Lima](https://lima-vm.io/) (`brew install lima`)
- [Tailscale](https://tailscale.com/) account with auth key
- [Just](https://github.com/casey/just) (`brew install just`)

### Setup Cluster
```bash
# Set up environment variables
echo "K3S_VPN_AUTH_KEY=your-tailscale-auth-key" > .env

# Start VMs
just vm-control-up
just vm-agent-up

# Deploy Kueue
kubectl apply -k infra/kueue/base/
```

### Run Example Job
```bash
kubectl apply -f examples/kueue-hello-world/job.yaml
kubectl get jobs -w
```

## � Dev Sessions (Velda-like)

QWEX can spin up an ephemeral "machine" as a Pod with a persistent home directory (PVC) and an SSH server, closely mirroring Velda's interactive session model:

- Persistent state: a PVC is mounted so changes in $HOME survive pod restarts.
- Sticky sessions: keep the same pod alive while you work; re-attach via port-forward.
- VS Code Remote: connect over SSH via `kubectl port-forward` (no node-level SSH needed).

Prerequisites
- A Kubernetes cluster and kubectl context
- The controller running locally: `just ctrl-dev`

Create a dev machine and connect
```fish
# 1) Create the machine (returns a UUID)
set MID (just machine-create)
echo Created machine $MID

# 2) Port-forward SSH to localhost:2222
just machine-port-forward $MID

# In another terminal, connect with VS Code Remote-SSH:
# Host: 127.0.0.1  Port: 2222  User: dev  (password generated per session)
# Or open a shell:
ssh -p 2222 dev@127.0.0.1
```

Notes
- The SSH user is `dev`; the password is generated per session and stored in a Kubernetes Secret named `qwex-<id>-auth`.
- The Pod listens on port 2222; we recommend using `kubectl port-forward` rather than exposing a Service.
- By default, resources live in the `default` namespace; set `QWEX_NAMESPACE` to change it. Set `QWEX_STORAGE_CLASS` to control storage class.
- You can override the SSH image with `QWEX_SSH_IMAGE` (default `lscr.io/linuxserver/openssh-server:latest`).

Cleanup
```fish
just machine-delete $MID
```

## �📁 **Project Structure**

```
qwex/
├── apps/
│   ├── controller/          # FastAPI job API server
│   └── cli/                # Command-line client
├── packages/
│   └── qwex-client/        # Generated Python client library
├── infra/
│   ├── kueue/             # Kueue configurations
│   ├── lima/              # VM configurations
│   └── controller/        # Controller deployment manifests
├── examples/
│   └── kueue-hello-world/ # Sample job definitions
└── Justfile               # Development automation
```

## 🔧 **Development**

### API Server Development
```bash
cd apps/controller
uv run fastapi dev src/main.py --reload
```

### Client Development
```bash
cd apps/cli
# Auto-generate client from API
uv run openapi-generator-cli generate -i http://localhost:8000/openapi.json
```

### Testing
```bash
# Run unit tests
uv run pytest

# Run integration tests (requires cluster)
just test-integration
```

## 🎯 **Roadmap**

### Phase 1: Core API (Current)
- FastAPI job submission and management
- Kubernetes/Kueue integration
- Basic CLI client

### Phase 2: Enhanced UX
- Web dashboard
- Advanced CLI features
- Job templates and dependencies

### Phase 3: Production Ready
- Authentication and RBAC
- Multi-cluster support
- Monitoring and metrics

### Phase 4: Enterprise Features
- GPU scheduling
- Cost optimization
- Advanced workflow orchestration
