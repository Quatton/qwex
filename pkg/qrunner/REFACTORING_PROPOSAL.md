# Runner Refactoring Proposal

## Current Issues

1. **Binary mounting is fragile**: Host macOS binary won't work in Linux containers
2. **Image spec location unclear**: Should it be in JobSpec or runner config?
3. **Mixed concerns**: LocalRunner and K8sRunner are fundamentally different
4. **Over-engineering**: Do we need LocalRunner inside containers?

## Proposed Architecture

### 1. Separate Packages by Execution Model

```
pkg/qrunner/
    interface.go    # Runner interface
    types.go        # Shared types (JobSpec, Run, RunStatus)

pkg/qrunner/local/
    runner.go       # LocalRunner - runs directly on host

pkg/qrunner/docker/
    runner.go       # DockerRunner - manages Docker containers
    
pkg/qrunner/k8s/
    runner.go       # K8sRunner - manages K8s Jobs
```

### 2. Add Image to JobSpec

```go
type JobSpec struct {
    Name       string
    Command    string
    Args       []string
    Env        map[string]string
    WorkingDir string
    
    // Container-specific (nil/empty for LocalRunner)
    Image      string  // "python:3.11" or ""
    
    // Future: resources, volumes, etc.
}
```

### 3. Remove Binary Mounting - Track from Host

**Current (complex):**
```
DockerRunner → Mount qwex binary → Run "qwex run --local cmd" → LocalRunner tracks
```

**Proposed (simple):**
```
DockerRunner → Run cmd directly → DockerRunner tracks via Docker API
```

**Implementation:**

```go
func (r *DockerRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
    // Determine image
    image := spec.Image
    if image == "" {
        image = r.defaultImage // fallback
    }
    
    // Create container with ORIGINAL command (no wrapper!)
    container := &container.Config{
        Image: image,
        Cmd:   append([]string{spec.Command}, spec.Args...),
        Env:   envMapToSlice(spec.Env),
    }
    
    resp, err := r.client.ContainerCreate(ctx, container, hostConfig, nil, nil, "qwex-"+runID)
    
    // Track status via Docker API (no binary needed!)
    go r.trackContainer(ctx, containerID, run)
    
    return run, nil
}

func (r *DockerRunner) trackContainer(ctx context.Context, containerID string, run *Run) {
    // Poll Docker API for status
    statusCh, errCh := r.client.ContainerWait(ctx, containerID, container.WaitConditionNotRunning)
    
    select {
    case status := <-statusCh:
        run.ExitCode = &status.StatusCode
        if status.StatusCode == 0 {
            run.Status = RunStatusSucceeded
        } else {
            run.Status = RunStatusFailed
        }
    case err := <-errCh:
        run.Status = RunStatusFailed
        run.Error = err.Error()
    }
    
    // Save to run.json
    r.saveRun(run)
}
```

### 4. Benefits

**Simplicity:**
- No binary compatibility issues
- No mounting complexity
- No init containers needed
- Direct command execution

**Flexibility:**
- Image per job (not per runner)
- Users can mix images: `qwex run --image=python:3.11 python script.py`
- Works with any container runtime

**Consistency:**
- DockerRunner tracks via Docker API
- K8sRunner tracks via K8s API
- LocalRunner tracks via process API
- Each uses native tooling!

### 5. Trade-offs

**What we lose:**
- Unified "qwex run --local" execution path
- LocalRunner inside containers (not needed!)

**What we gain:**
- Simpler architecture
- No cross-compilation
- No binary distribution
- Standard container patterns

## Migration Path

1. **Phase 1**: Add `Image` to `JobSpec`
2. **Phase 2**: Make DockerRunner track directly (remove binary mount)
3. **Phase 3**: Split packages (optional, for cleaner separation)
4. **Phase 4**: Update K8sRunner similarly

## Question for Discussion

**Do we even need LocalRunner inside containers?**

The whole point of DockerRunner is to manage containers from the outside. We don't need LocalRunner inside - we can track everything via Docker API!

This is how every other container orchestration tool works:
- Docker Compose - tracks via Docker API
- Kubernetes - tracks via K8s API  
- Nomad - tracks via driver API

We should follow the same pattern!
