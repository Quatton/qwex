# Runner Design Decisions

## Problem 1: How do users run jobs in custom Docker images?

### ❌ Bad Approach: Force users to build images with qwex
```dockerfile
FROM python:3.11
COPY qwex /usr/local/bin/qwex  # Users have to rebuild their images!
```

**Problems:**
- Users must rebuild every image
- Different architectures (arm64, amd64) need different binaries
- Version management nightmare
- Goes against Docker best practices

### ✅ Good Approach: Mount qwex binary from host

```go
// DockerRunner mounts the host's qwex binary into ANY container
mounts := []mount.Mount{
    {Source: "/path/to/qwex", Target: "/qwex/bin/qwex", ReadOnly: true},
}
```

**Benefits:**
- Users can use **ANY base image**: `python:3.11`, `node:20`, `rust:latest`, etc.
- No image rebuilding required
- Automatic architecture matching (host qwex = container qwex)
- Single qwex binary for all containers

**How it works:**
1. User: `qwex run --backend=docker --image=python:3.11 "python script.py"`
2. DockerRunner mounts host qwex binary → `/qwex/bin/qwex` in container
3. Container runs: `/qwex/bin/qwex run --local python script.py`
4. LocalRunner inside container executes: `python script.py`

## Problem 2: Cyclic dependency with generated client code

### The Cycle
```
pkg/qapi (server) → needs pkg/qrunner
pkg/qrunner → needs config
config in pkg/qsdk → needs pkg/client (generated)
pkg/client → generated from pkg/qapi OpenAPI spec
```

### ✅ Solution 1: Separate configs
- **Runner config** (ContainerConfig, ResourceRequirements) → lives in `pkg/qrunner`
- **API client config** (BaseURL, APIVersion) → lives in `pkg/qsdk`

These are **different concerns** and don't need to be mixed!

### ✅ Solution 2: Safe generation workflow

```bash
just gen
# 1. Backup old gen.go → gen.go.bak
# 2. Generate new gen.go
# 3. Test compilation
# 4. If OK: delete backup
# 5. If ERROR: restore backup, abort
```

This prevents broken gen.go from killing the build.

### ✅ Solution 3: QwexRunner uses minimal interface (future)

Instead of depending on generated `pkg/client`:

```go
// Minimal HTTP client interface - no codegen needed!
type JobAPIClient interface {
    SubmitJob(ctx, request) (jobID string, error)
    GetJob(ctx, jobID) (*JobResponse, error)
    CancelJob(ctx, jobID) error
}

type QwexRunner struct {
    client JobAPIClient  // Can be generated client OR hand-written HTTP calls
}
```

This breaks the cycle because `QwexRunner` doesn't import `pkg/client` directly.

## Problem 3: K8s vs Kueue Runner relationship

### ❌ Wrong: Deep inheritance
```go
type KueueRunner struct {
    k8sRunner *K8sRunner  // Wrapping/delegation
}
```

### ✅ Right: Label-based configuration
```go
// K8sRunner with optional queue label
func NewK8sRunner(namespace, image string, queueName *string) (*K8sRunner, error) {
    // If queueName != nil, add kueue.x-k8s.io/queue-name label
}
```

**Why?** Kueue is just a K8s admission controller that watches for queue labels. There's no need for a separate runner - just add the label!

## Summary

| Runner       | Execution Environment | qwex Binary Source                              |
| ------------ | --------------------- | ----------------------------------------------- |
| LocalRunner  | Host machine          | Host installation                               |
| DockerRunner | Docker container      | **Mounted from host**                           |
| K8sRunner    | Kubernetes Pod        | Could mount from hostPath or use init container |
| QwexRunner   | Remote server         | Not needed (API call only)                      |

**Key Insight:** Mounting the binary from host is the most flexible approach. It allows users to use any base image without modification.
