# qrunner Architecture

## Overview

The qrunner package implements a **Runner/Watcher pattern** for executing and monitoring jobs across multiple backends (local processes, Docker containers, Kubernetes pods).

## Core Concepts

### 1. Runner (Executor)
Handles job **lifecycle** - submission, cancellation, and state transitions.

**Responsibilities:**
- Submit jobs and return immediately (fire-and-forget)
- Start/stop execution
- Save initial state to filesystem
- Clean up resources after completion

**What Runners DON'T do:**
- Block waiting for completion (that's Watcher's job)
- Poll for status updates
- Stream logs in real-time
- Call qwexcloud APIs

### 2. Watcher (Observer) - Future
Handles job **monitoring** - status tracking, log streaming, and state observation.

**Responsibilities:**
- Poll execution backend (Docker API, filesystem, K8s API)
- Stream logs in real-time
- Update run state based on backend status
- Provide attach/detach capability

**What Watchers DON'T do:**
- Execute or control jobs
- Modify runner configuration
- Make decisions about job lifecycle

### 3. Why Separation?

**Current (coupled):**
```go
run := runner.Submit(spec)     // Submits
runner.Wait(run.ID)            // Blocks until done
// CLI must stay open, can't detach
```

**Future (separated):**
```go
run := runner.Submit(spec)     // Returns immediately
// Optional: attach watcher
watcher.Stream(run.ID)         // Can detach/reattach
```

## Runner Delegation Pattern

Each runner wraps command execution in a different environment:

```
User: qwexctl run --backend=local "python train.py"
  → LocalRunner: executes "python train.py" directly on host

User: qwexctl run --backend=docker "python train.py"
  → DockerRunner: creates container, runs "python train.py"
  → Direct execution (NO binary mounting)
  → Uses specified image (e.g., python:3.12-slim)

User: qwexctl run --backend=k8s "python train.py"
  → K8sRunner: creates Pod/Job, runs "python train.py"
  → K8s manages pod lifecycle
  → Logs via K8s API

User: qwexctl run --backend=kueue "python train.py"
  → KueueRunner: creates Job with queue labels
  → Kueue admits job when resources available
  → Then same as K8sRunner
```

## Backend Implementations

### Local Runner
**Execution:** Spawns subprocess via `os/exec`  
**State:** Writes to `.qwex/runs/<runID>/run.json`  
**Cleanup:** Process terminates, state persisted  

**Current:** Wait() blocks on process completion  
**Future Watcher:** Poll filesystem for run.json updates

### Docker Runner
**Execution:** Creates container via Docker API  
**State:** Writes to `.qwex/runs/<runID>/run.json` + Docker metadata  
**Cleanup:** Container auto-removed after completion (ephemeral like K8s pods)  

**Current:** Wait() blocks on Docker API ContainerWait  
**Future Watcher:**
- Poll Docker API: `ContainerInspect()` for status
- Stream logs: `ContainerLogs()` with follow=true
- Docker daemon IS the execution daemon (no need for qwex daemon)

### K8s Runner
**Execution:** Creates Job resource via K8s API  
**State:** K8s etcd (authoritative) + optional local cache  
**Cleanup:** Pods cleaned up by K8s (or kept based on policy)  

**Future Watcher:**
- Watch K8s API: `Watch()` on Job resource
- Stream logs: `PodLogs()` with follow=true
- K8s API server IS the daemon (no need for qwex daemon)

## Shared Components

### 1. Interface & Types (interface.go)
All runners implement the Runner interface:
- `Submit(JobSpec) → Run`
- `Wait(runID) → Run`
- `GetRun(runID) → Run`
- `Cancel(runID)`
- `ListRuns(status?) → []Run`

### 2. Container Configuration (container_config.go)
Shared between DockerRunner, K8sRunner, KueueRunner:
- `ContainerConfig`: image, resources, mounts, network
- `ResourceRequirements`: CPU/memory (portable format)
- `Mount`: volume mounting specification

### 3. Status & Utilities
Common patterns:
- `RunStatus` enum (pending, running, succeeded, failed, cancelled)
- Timestamp handling (CreatedAt, StartedAt, FinishedAt)
- Run state persistence (run.json)

## Runner vs Watcher: Backend Comparison

This table clarifies how responsibilities are divided across different backends.

| Feature                                 | Local Backend                                     | Docker Backend                              | K8s / Kueue Backend                     |
| :-------------------------------------- | :------------------------------------------------ | :------------------------------------------ | :-------------------------------------- |
| **Runner Action**<br>(`Submit`)         | Spawns `exec.Cmd`<br>(detached process)           | Calls Docker API<br>(`ContainerCreate`)     | Calls K8s API<br>(`Job` resource)       |
| **State Source**                        | Filesystem<br>(`.qwex/runs/<id>/run.json`)        | Docker Daemon<br>(`ContainerInspect`)       | K8s API Server<br>(`Job` Status)        |
| **Watcher Action**<br>(`Wait`/`Stream`) | Polls `run.json` & PID<br>Tails `stdout.log` file | Polls Docker API<br>Streams `ContainerLogs` | Watches K8s Events<br>Streams `PodLogs` |
| **Persistence**                         | Local Disk                                        | Docker Storage                              | etcd (via K8s)                          |
| **Primary User**                        | `qwexctl` (CLI)                                   | `qwexctl` (CLI)                             | `qwexctl` (CLI) & `qwexcloud`           |

### Usage Patterns

1.  **qwexctl (CLI):**
    *   Uses **Runner** to submit jobs (fire-and-forget).
    *   Uses **Watcher** to attach to running jobs (local or remote).
2.  **qwexcloud (Server):**
    *   Uses **Watcher** (K8s backend) to observe cluster state and update its own database.
    *   *Does not usually use Runner* (unless it's orchestrating jobs itself).

## Architecture Decision: Watcher vs Daemon

### Why Watcher (Chosen)
✅ **Lightweight:** Just a library that polls backend APIs  
✅ **No Process Management:** Leverages existing daemons (Docker, K8s)  
✅ **Simpler:** No IPC, no daemon lifecycle  
✅ **Flexible:** Can be used from CLI or server  

### Why NOT Daemon
❌ **Unnecessary:** Docker daemon already exists  
❌ **Complexity:** Need process management, IPC protocol  
❌ **Overkill:** For local/docker use cases  

### Exception: Optional qwexctl daemon
For **local-only** execution (no Docker), qwexctl could spawn a lightweight daemon:
- Supervise background processes
- Track multiple concurrent runs
- Provide unified API across backends

**But:** Keep it optional. Watcher should work without daemon.

### qwexcloud: Microservice Pattern
For remote execution (K8s/Kueue backends):
```
qwexctl → HTTP API → qwexcloud microservice
                   → K8s API server (the daemon)
                   → Submits Jobs/Pods
```
No need for separate daemon - K8s API server fills that role.

## Strategic Decision: Direct vs. Mediated Access

You might ask: **"Why do we need qwexcloud if qwexctl can talk to K8s directly?"**

### 1. Direct Access (The "kubectl" Model)
*   **How it works:** `qwexctl` uses `~/.kube/config` to talk directly to the K8s API.
*   **Pros:** Simple, no server to maintain, great for small teams/admins.
*   **Cons:**
    *   **Credentials:** Every user needs a K8s ServiceAccount/Certificate.
    *   **History:** When K8s deletes the Pod (Garbage Collection), the run history is GONE.
    *   **Complexity:** Users need to understand K8s concepts (namespaces, quotas).

### 2. Mediated Access (The "qwexcloud" Model)
*   **How it works:** `qwexctl` talks to `qwexcloud` (REST/gRPC), which talks to K8s.
*   **Pros:**
    *   **Persistence:** `qwexcloud` stores run history in SQL forever, even after Pods are deleted.
    *   **Abstraction:** Users just need a `qwex` token, not K8s credentials.
    *   **Multi-Cluster:** One `qwexcloud` can dispatch to 10 different K8s clusters transparently.
    *   **Webhooks:** Can trigger Slack/Email notifications on completion (K8s can't do this easily).
*   **Cons:** More infrastructure to maintain.

**Verdict:**
*   **MVP:** Start with **Direct Access** (using `pkg/k8s` in CLI).
*   **Production:** Use **Mediated Access** (`qwexcloud`) for teams, history, and security.

## Current Implementation Status

### ✅ Completed
- ✅ Runner pattern implemented (Submit returns immediately)
- ✅ LocalRunner with subprocess execution
- ✅ DockerRunner with direct command execution (no binary mounting)
- ✅ UUIDv7 for lexicographically sortable run IDs
- ✅ Container auto-cleanup (ephemeral execution)
- ✅ Proper log demultiplexing (stdcopy for Docker)
- ✅ Config-based backend selection
- ✅ Structured logging (slog via qlog wrapper)

### 🔄 In Progress / TODO
- 🔄 Watcher pattern (currently Wait() blocks)
- 🔄 Fire-and-forget mode (`--detach` flag)
- 🔄 Attach/reattach capability
- 📋 K8sRunner completion
- 📋 Kueue integration
- 📋 Remote execution (qwexcloud API)

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                        qwexctl                           │
│                    (CLI Agent)                           │
└────┬─────────────────────────────────────────────────┬───┘
     │                                                 │
     │ Submit                                   Watch  │
     ▼                                          (future)
┌─────────────┐                              ┌──────────────┐
│   Runner    │                              │   Watcher    │
│  (Execute)  │                              │  (Observe)   │
└──────┬──────┘                              └───────┬──────┘
       │                                             │
       │ Creates                               Polls │
       ▼                                             ▼
┌─────────────────────────────────────────────────────────┐
│              Execution Backend                          │
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │   Process   │  │   Docker    │  │ Kubernetes  │   │
│  │  (os/exec)  │  │  (Daemon)   │  │ (API Server)│   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────┘
       │                     │                  │
       └─────────────────────┴──────────────────┘
                             │
                    State persisted to
                    .qwex/runs/<runID>/
```

## Data Flow

### Submit Flow (Fire-and-Forget)
```
1. qwexctl run -- python script.py
2. Runner.Submit(spec)
   - Generate UUIDv7 run ID
   - Create .qwex/runs/<runID>/
   - Start execution (subprocess/container/job)
   - Write initial state: status=running
   - Return immediately
3. qwexctl prints: "Run ID: 019aa011..."
```

### Watch Flow (Future)
```
1. qwexctl run --watch -- python script.py
   OR
   qwexctl attach 019aa011...
   
2. Watcher.Stream(runID)
   - Poll backend for status
   - Stream logs in real-time
   - Update local state file
   - Handle Ctrl+C (detach, don't cancel)
   
3. User can Ctrl+C and re-attach later
```

### Detached Completion
```
1. Job runs in background
2. Runner monitors completion (async via Wait())
3. Final state written: status=succeeded/failed
4. Container/pod cleaned up
5. Logs persisted to .qwex/runs/<runID>/stdout.log
```

## Design Decisions

### 1. No Binary Mounting
**Decision:** Run commands directly in containers, don't mount qwex binary

**Rationale:**
- ❌ Binary compatibility issues (macOS arm64 → Linux amd64)
- ❌ Requires custom base images
- ✅ Users can use ANY image (python:3.12, node:20, etc.)
- ✅ Simpler: just run the command in the container

### 2. UUIDv7 for Run IDs
**Decision:** Use UUIDv7 instead of UUIDv4

**Benefits:**
- ✅ Lexicographically sortable (timestamp embedded)
- ✅ Better database indexing (sequential IDs)
- ✅ Human-readable creation time
- ✅ Natural chronological ordering: `ls .qwex/runs/` shows newest last

### 3. Ephemeral Containers
**Decision:** Auto-remove Docker containers after completion

**Rationale:**
- Like K8s pods: containers are ephemeral
- State saved in volumes (.qwex/runs/)
- No container clutter in `docker ps -a`
- Logs captured before removal

### 4. Config-Based Backend Selection
**Decision:** Backend selected via qwex.yaml, not just command flags

**Rationale:**
- Project-specific: Docker for local dev, K8s for prod
- Consistent across team members
- Can be overridden with `--backend` flag if needed

### 5. Structured Logging (slog)
**Decision:** Use stdlib slog for server logging, keep fmt.Printf for CLI UX

**Server (qwexcloud):** Structured logs for observability
```go
logger.Info("request started", "method", "POST", "path", "/api/runs")
```

**CLI (qwexctl):** Clean user-facing output
```go
fmt.Printf("✓ Run submitted successfully!\n")
```

## Naming Significance

- **Runner** = Executes the work (active, transitive)
- **Watcher** = Observes and reports (passive, read-only)
- **Agent** = Acts on behalf of user (qwexctl is the agent)
- **Daemon** = Long-running process that manages things (optional for local)

## Anti-Patterns to Avoid

❌ **Runner calling qwexcloud API**
- Creates circular dependency
- Violates separation of concerns
- Makes local execution depend on cloud

❌ **Watcher modifying run state**
- Watcher should be read-only observer
- Only Runner should modify state

❌ **Blocking Submit()**
- Submit should return immediately
- Use Wait() or Watcher for monitoring

❌ **Tight coupling to execution backend**
- Keep Runner interface backend-agnostic
- Abstract away Docker/K8s details

## Future: Multi-Backend Workflows

```yaml
# qwex.yaml
stages:
  - name: test
    backend: local
    command: pytest
  
  - name: train
    backend: docker
    image: pytorch/pytorch:latest
    command: python train.py
    
  - name: deploy
    backend: kueue
    queue: gpu-queue
    command: python deploy.py
```

## References

- [Runner Interface](./interface.go)
- [Docker Runner Implementation](./docker.go)
- [Local Runner Implementation](./local.go)
- [K8s Runner Implementation](./k8s.go)
- [Container Configuration](./container_config.go)
- [Logging Package](../qlog/logger.go)

