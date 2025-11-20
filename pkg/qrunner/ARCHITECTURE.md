# Runner Architecture

This document explains how different runners work together in a delegation pattern.

## Pattern: Wrapper/Delegation (NOT Inheritance)

Each runner wraps command execution in a different environment:

```
User: qwex run --backend=local "echo hello"
  → LocalRunner: executes "echo hello" directly on host

User: qwex run --backend=docker "echo hello"
  → DockerRunner: creates container with ["qwex", "run", "--local", "echo", "hello"]
  → Inside container, LocalRunner: executes "echo hello"

User: qwex run --backend=k8s "echo hello"
  → K8sRunner: creates Pod with ["qwex", "run", "--local", "echo", "hello"]
  → Inside Pod, LocalRunner: executes "echo hello"

User: qwex run --backend=kueue "echo hello"
  → KueueRunner: creates Job with Kueue labels + ["qwex", "run", "--local", "echo", "hello"]
  → Kueue admits Job → Pod starts
  → Inside Pod, LocalRunner: executes "echo hello"
```

## Shared Components

### 1. Interface & Types (interface.go)
All runners implement the same Runner interface:
- Submit(JobSpec) → Run
- Wait(runID) → Run
- GetRun(runID) → Run
- Cancel(runID)
- ListRuns(status?) → []Run

### 2. Container Configuration (container_config.go)
Shared between DockerRunner, K8sRunner, KueueRunner:
- ContainerConfig: image, resources, mounts, network
- ResourceRequirements: CPU/memory (portable format)
- Mount: volume mounting specification
- WrapCommandForLocal(): wraps command for delegation to LocalRunner

### 3. Status & Utilities
Common patterns:
- RunStatus enum (pending, running, succeeded, failed, cancelled)
- Wait() polling pattern (used by all runners)
- Timestamp handling (CreatedAt, StartedAt, FinishedAt)

## What Each Runner Does

### LocalRunner (local.go)
- Runs commands directly on host machine using os/exec
- Creates .qwex/runs/<runID>/ directory structure
- Writes run.json with status, logs to stdout.log
- Tracks processes in memory for cancellation
- Used by other runners inside containers/pods

### DockerRunner (docker.go)
- Calls Docker API to create/start container
- Mounts .qwex/runs/<runID> from host into container
- Runs "qwex run --local <command>" inside container
- LocalRunner inside container writes to mounted directory
- Host can read run.json from mounted directory
- Container config: image, mounts, resources, env vars

### K8sRunner (k8s.go)
- Uses Kubernetes client to create Job
- Could wrap command with WrapCommandForLocal() (currently runs directly)
- Queries Job/Pod status via K8s API
- Logs via kubectl logs (stored in Pod, not shared filesystem)
- Container config: similar to Docker but using K8s primitives

### KueueRunner (future)
- Extends K8sRunner by adding Kueue queue labels
- Job starts suspended, Kueue admits it when resources available
- Everything else same as K8sRunner
- Could be implemented as:
  ```go
  type KueueRunner struct {
      *K8sRunner
      queueName string
  }
  func (r *KueueRunner) Submit(ctx, spec) {
      // Add queue label before calling K8sRunner.Submit()
      spec.Metadata["kueue.x-k8s.io/queue-name"] = r.queueName
      return r.K8sRunner.Submit(ctx, spec)
  }
  ```

## Key Insight: Why NOT Deep Nesting

❌ WRONG: DockerRunner doesn't call K8sRunner
❌ WRONG: K8sRunner doesn't call DockerRunner
✅ RIGHT: They're independent, but share container config concepts

Docker and K8s both need to:
- Specify an image
- Mount volumes
- Set resource limits
- Configure networking
- Pass environment variables

So they share ContainerConfig types and helper functions, but each
implements its own Submit/Wait/GetRun/Cancel using different APIs
(Docker API vs Kubernetes API).

## Mounting & Volume Sharing

### DockerRunner
- Mounts host path into container: /host/path:/container/path
- Example: ~/.qwex/runs/abc-123 → /qwex/runs/abc-123
- LocalRunner inside writes to /qwex/runs/abc-123
- Host sees updates at ~/.qwex/runs/abc-123

### K8sRunner
- Could use PersistentVolumeClaim (PVC) for shared storage
- Or use hostPath (if single-node cluster like k3d)
- Or use emptyDir (ephemeral, pod-only)
- Currently stores logs in Pod (kubectl logs), no shared filesystem

This is why DockerRunner and K8sRunner DON'T share mounting implementation:
- Docker: simple bind mounts
- K8s: complex volume types (PVC, ConfigMap, Secret, hostPath, etc.)

But they DO share the Mount type definition and concepts!
