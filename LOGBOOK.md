> For the sake of academic transparency, this logbook is created on Sun Oct 19 2025, which is way past the beginning date of this project. I will not backdate entries on Week 1 - 2 to misrepresent the actual timeline of development.

## Week 3: Oct 16 - Oct 22, 2025

### Goals

- Make a simple kueue job submission controller that works end-to-end.
- It should relay command from the CLI to kueue via the FastAPI controller, then to the kueue workload in the cluster.

### Considerations

- I thought about making a client-side cluster, removing the kueue and kubernetes entirely. The idea is to not make a job scheduler but only a coordinator that checks if jobs are running, and the user just uses it as a "spreadsheet" to coordinate this with their peers.
  - However, I decided against this because 
    - It would be reinventing the wheel
    - This makes actual distributed computing impossible.
    - Having to suspend someone else's job is not feasible in a client-side only model.
- We will stick to the motto of "let's use great technologies to build accessible applications", rather than "let's use accessible technologies to build great applications".
- Renamed to Qwex
  
### Activities

- Add RBAC manifests for the controller to manage kueue workloads.
  > Since this RBAC manifests only live in side the 

## What is Qwex?

Queued Workspace-Aware EXecutor (Qwex) is a modular run-this-on-another-machine system that consists of:

1. Backend-agnostic Zero-config Command Relay: Backend-agnostic is quite a scam because you need to setup an SSH server first. The idea is that once you have an SSH server, you can run `qwex batch python main.py` and it will run that job, and streams the output back to you. Wait, but do I need `scp`? No. `rsync`? No. `rsshfs`? No. Qwex will handle file transfer for you, so you don't need to worry about it.
2. Kueue-based Job Scheduling: While you can use Slurm as a backend, we propose another architectural design using [Kueue](https://kueue.sigs.k8s.io/). Kueue is a Kubernetes-native job scheduler that allows fine-grained control over job scheduling and resource allocation. Qwex leverages Kueue to manage job queues across multiple nodes, ensuring efficient resource utilization and job prioritization.

So can you just use `kubectl`? Yes.
Can you use `qwex` without Kueue? Yes.
Can you use `qwex`'s SDK to access your jobs programmatically? Yes.
It's modular and flexible.

## Week 6: Nov 6 - Nov 12, 2025

### Reevaluate Project Direction

- I'm using Kubernetes.
- It's easier to set up (trust me)
- It scales better.
- Easier to deploy.

Architecture: not yet finalized

## Week 8: Nov 20, 2025

### Runner Architecture Finalized

After extensive design discussions, we've finalized the architecture for Qwex's execution layer. The goal is to make Qwex a **zero-init, filesystem-level capture tool** that works with any code and any tracking tool.

#### Core Concepts

**Job vs Run**
- **Job**: Template/definition of work (the recipe)
  - Defines: command, environment, dependencies, configuration
  - Reusable and versioned
  - Example: "train model X with config Y"
- **Run**: Specific execution instance of a Job (one baking session)
  - Each run has unique ID, lifecycle, logs, outputs, metrics
  - Multiple runs can come from same job (retries, experiments, different params)
  - Tracks: status, timestamps, exit code, artifacts

**Runner vs Run Relationship**
- **Run**: Pure data model (state object)
  - Contains: ID, JobID, Status, CreatedAt, StartedAt, FinishedAt, ExitCode, Error, Metadata
  - Immutable/append-only
  - Persisted to filesystem or DB
- **Runner**: Execution engine (behavior/logic)
  - Implements: `Submit(ctx, jobSpec) (*Run, error)`, `GetRun(ctx, runID) (*Run, error)`, `Cancel(ctx, runID) error`
  - Stateless or minimal state (just config like API URLs, credentials, directories)
  - Two implementations:
    - **LocalRunner**: executes jobs on current machine
    - **QwexCloudRunner**: submits jobs to Qwex Cloud API (cloud execution uses LocalRunner internally)

#### Run Lifecycle States

Simplified state machine for MVP:
```
PENDING (submitted + queued + initializing)
  ↓
RUNNING (actively executing)
  ↓
SUCCEEDED | FAILED | CANCELLED
```

Future expansion:
```
PENDING → INITIALIZING → RUNNING → FINALIZING → SUCCEEDED/FAILED/CANCELLED
```

#### Directory Structure

**Nested structure** (matches wandb/mlflow patterns):
```
project/
  train.py
  out/                    # conventional output dir (user writes here)
    model.pth
    metrics.json
  .qwex/
    runs/
      abc123/
        run.json          # execution metadata only
        stdout.log        # combined console output
        stderr.log        # or separate stderr
        files/            # captured artifacts (copied from out/)
          model.pth
          metrics.json
        artifacts.json    # auto-generated manifest
```

**Why nested?**
- Single source of truth: everything for run X in one place
- Easy cleanup: `rm -rf .qwex/runs/abc123/`
- Easy archival: `tar -czf abc123.tar.gz .qwex/runs/abc123/`
- Matches industry patterns (wandb, mlflow, tensorboard)

#### Artifact Auto-Capture

**Zero-init approach**: Users just write to `out/` (or configured dir), qwex auto-captures.

**Default convention:**
```python
# User code - no qwex-specific logic needed
import torch
torch.save(model.state_dict(), "out/model.pth")
```

**Configuration** (`.qwex/config.yaml`):
```yaml
artifacts:
  watch_directories:
    - out              # default
    # - checkpoints    # user can add more
    # - models
  ignore_patterns:
    - "*.tmp"
    - "*.log"
    - "__pycache__"
    - ".git"
  max_file_size_mb: 1000
```

**Implementation**: Post-run directory scan (not real-time fsnotify)
- After command exits, scan configured directories
- Copy files to `.qwex/runs/<runId>/files/`
- Generate `artifacts.json` manifest with checksums

**CLI override:**
```bash
qwex run python train.py --local --watch outputs,models
```

#### Coexistence with Tracking Tools

**Design principle**: Qwex is **execution layer**, not **tracking layer**

**What qwex stores:**
- Execution metadata: status, command, exit code, timestamps
- Console output: stdout/stderr
- Artifacts: files from watched directories

**What qwex does NOT store:**
- Metrics/plots (leave to wandb/mlflow)
- Hyperparameters (except as command args)
- Training checkpoints (unless in watched dir)

**Example with wandb:**
```python
import wandb
import torch

wandb.init(project="my-project")

# Train model
# ...

# Both qwex and wandb capture from out/
torch.save(model.state_dict(), "out/model.pth")
wandb.save("out/model.pth")
```

**Result:**
- Qwex captures: `out/model.pth` → `.qwex/runs/abc123/files/`
- Wandb captures: `out/model.pth` → `wandb/run-xyz/files/`
- No conflicts — orthogonal systems

**Environment variables (optional):**
```bash
QWEX_RUN_ID=abc123
QWEX_RUN_DIR=/path/to/.qwex/runs/abc123
```

User code can optionally use these to link tracking runs:
```python
import wandb
import os

wandb.init(
    project="my-project",
    tags=[f"qwex:{os.getenv('QWEX_RUN_ID')}"]
)
```

#### User Experience

**Setup (optional):**
```bash
cat > .qwex/config.yaml
artifacts:
  watch_directories:
    - out
    - models
```

**Code (language-agnostic):**
```python
# Just use "out/" - simple convention
torch.save(model.state_dict(), "out/model.pth")
```

**Run:**
```bash
$ qwex run python train.py --local
⚙️  Run abc123 started
⏳ Running python train.py...
✅ Run abc123 succeeded in 2m 15s
📦 Captured 1 artifact (50 MB)
```

**View artifacts:**
```bash
$ qwex artifacts abc123
Run abc123 artifacts:
  out/model.pth (50.0 MB)

$ ls .qwex/runs/abc123/files/
out/
```

#### Key Benefits

✅ **Zero burden**: just write to `out/` (or configured dir)  
✅ **Zero init**: no SDK calls, no `wandb.init()` equivalent  
✅ **Language-agnostic**: works with Python, R, Julia, Rust, etc.  
✅ **Tool-agnostic**: coexists with wandb/mlflow/tensorboard  
✅ **Conventional**: `out/` is standard (like `node_modules/`, `build/`)  
✅ **Simple implementation**: post-run directory copy (no fsnotify complexity)  
✅ **Cloud-ready**: same approach works for local and cloud runs  

#### Next Steps

1. Update `pkg/qsdk/runner/interface.go` with Job/Run separation and lifecycle states
2. Implement LocalRunner with artifact capture
3. Implement QwexCloudRunner with API submission
4. Add CLI commands: `qwex run`, `qwex artifacts`, `qwex status`
5. Add tests for both runners

## Week 9: Nov 26, 2025

### Qwex Protocol (QWP) v1.0

After extensive design discussions, we're introducing the **Qwex Protocol (QWP)** — an open protocol for ML run orchestration. The goal is to make qwex a protocol, not just a tool.

#### Design Philosophy

- **Open protocol, flexible implementation**: Protocol is OSS, servers implement it however they want
- **No lock-in**: Your code doesn't know qwex exists. Remove `qwex run`, scripts still work
- **Coexists with W&B/MLflow**: qwex handles execution, they handle tracking

#### Protocol Manifest

Every qwex-compatible server exposes `/.well-known/qwex.json`:

```json
{
  "qwex": "1.0",
  
  "server": {
    "name": "string",
    "version": "string",
    "docs": "string (optional)"
  },
  
  "api": {
    "versions": ["v1"],
    "base": "/api"
  },
  
  "auth": {
    "type": "oauth2 | api-key | local | none",
    "spec": { }
  },
  
  "features": {
    "source": { },
    "artifacts": { },
    "runs": { }
  }
}
```

#### Auth Types

```json
// api-key (v1 focus)
"auth": {
  "type": "api-key",
  "spec": {
    "header": "X-API-Key"
  }
}

// local (for qwex-local daemon)
"auth": {
  "type": "local",
  "spec": {
    "keyFile": "~/.qwex/local-api-key"
  }
}

// oauth2 (future)
"auth": {
  "type": "oauth2",
  "spec": {
    "provider": "github",
    "authUrl": "/auth/login",
    "tokenUrl": "/auth/token"
  }
}
```

#### Features (Behavior Flags)

Features don't change API shape, they change behavior:

```json
"features": {
  "source": {
    "transfer": "presigned-upload | mount",
    "format": "git-bundle | tar | worktree",
    "maxSize": 104857600,
    "requireClean": true
  },
  
  "artifacts": {
    "enabled": true,
    "autoUpload": true,
    "patterns": ["*.pt", "*.onnx", "outputs/**"],
    "maxSize": 1073741824
  },
  
  "runs": {
    "wait": true,
    "cancel": true,
    "logs": true,
    "backends": ["local", "docker", "kueue"]
  }
}
```

#### Fixed API Routes (v1)

| Method   | Route                                      | Description                         |
| -------- | ------------------------------------------ | ----------------------------------- |
| `POST`   | `{base}/v1/source/upload-url`              | Get presigned URL for source upload |
| `POST`   | `{base}/v1/runs`                           | Submit run                          |
| `GET`    | `{base}/v1/runs`                           | List runs                           |
| `GET`    | `{base}/v1/runs/{id}`                      | Get run                             |
| `DELETE` | `{base}/v1/runs/{id}`                      | Cancel run                          |
| `GET`    | `{base}/v1/runs/{id}/logs`                 | Get logs                            |
| `GET`    | `{base}/v1/runs/{id}/wait`                 | Wait for completion                 |
| `GET`    | `{base}/v1/runs/{id}/artifacts`            | List artifacts                      |
| `GET`    | `{base}/v1/runs/{id}/artifacts/{name}/url` | Get artifact download URL           |
| `POST`   | `{base}/v1/runs/{id}/artifacts/upload-url` | Get artifact upload URL             |

#### Source Code Transfer

**Problem**: How does remote execution get your code?

**Solution**: Git bundle approach (strict mode)
- Must commit before run (enforces reproducibility)
- Client creates git bundle of committed code
- Bundle uploaded to S3 (for remote) or worktree created (for local)
- Every run tied to exact git SHA

**Local runs**: Git worktree (instant, no network)
```bash
git worktree add /tmp/qwex-runs/<run-id> <sha> --detach
# Container mounts this directory
# After run: git worktree remove ...
```

**Remote runs**: Git bundle + S3
```bash
git bundle create /tmp/repo.bundle --all
# Upload to s3://qwex/source/<run-id>/repo.bundle
# Container clones from bundle
```

**Benefits**:
- No GitHub token needed (bundle contains everything)
- Perfect reproducibility (exact SHA)
- `qwex checkout <run-id>` can recreate exact state
- Your working dir stays untouched while run executes

#### Example Manifests

**qwexcloud (production)**:
```json
{
  "qwex": "1.0",
  "server": { "name": "qwexcloud", "version": "1.0.0" },
  "api": { "versions": ["v1"], "base": "/api" },
  "auth": { "type": "api-key", "spec": { "header": "X-API-Key" } },
  "features": {
    "source": {
      "transfer": "presigned-upload",
      "format": "git-bundle",
      "maxSize": 104857600,
      "requireClean": true
    },
    "artifacts": {
      "enabled": true,
      "autoUpload": true,
      "patterns": ["*.pt", "outputs/**"]
    },
    "runs": {
      "wait": true,
      "cancel": true,
      "logs": true,
      "backends": ["kueue"]
    }
  }
}
```

**qwex-local (development)**:
```json
{
  "qwex": "1.0",
  "server": { "name": "qwex-local", "version": "1.0.0" },
  "api": { "versions": ["v1"], "base": "/api" },
  "auth": { "type": "local", "spec": { "keyFile": "~/.qwex/local-api-key" } },
  "features": {
    "source": {
      "transfer": "mount",
      "format": "worktree",
      "requireClean": true
    },
    "artifacts": { "enabled": false },
    "runs": {
      "wait": true,
      "cancel": true,
      "logs": true,
      "backends": ["local", "docker"]
    }
  }
}
```

#### Request/Response Types (v1)

```yaml
# POST /v1/source/upload-url
SourceUploadUrlRequest:
  sha: string
  size: integer

SourceUploadUrlResponse:
  url: string
  key: string
  expires: integer

# POST /v1/runs
SubmitRunRequest:
  name: string (optional)
  command: string
  args: string[]
  env: map[string]string
  source:
    sha: string
    key: string
  backend: string (optional)

RunResponse:
  id: string
  name: string
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled"
  command: string
  args: string[]
  createdAt: string (RFC3339)
  startedAt: string (optional)
  finishedAt: string (optional)
  exitCode: integer (optional)
  backend: string
  source:
    sha: string
  artifacts: Artifact[]

LogsResponse:
  stdout: string
  stderr: string

ArtifactUrlResponse:
  url: string
  expires: integer
```

#### Implementation Plan

**Phase 1: Protocol Foundation**
1. Create `docs/protocol/qwp-v1.md` — Full spec
2. Create `pkg/qwp/` — Go types for manifest + requests/responses
3. Create `api/qwp/openapi.yaml` — OpenAPI spec for v1 routes

**Phase 2: qwex-local Server**
4. Create local server implementing QWP v1
   - Auth: api-key (simple header check)
   - Source: mount (git worktree)
   - Runs: local + docker backends
   - Artifacts: disabled initially

**Phase 3: qwexctl Refactor**
5. Create `pkg/qwp/client.go` — Protocol client
6. Refactor qwexctl to use qwp client
   - `qwexctl init <server>` — Register server
   - `qwexctl run` — Use protocol

**Phase 4: qwexcloud Alignment**
7. Update qwexcloud to implement QWP v1
   - Add `/.well-known/qwex.json`
   - Align routes to spec
   - Add source upload endpoint

## Week 9: Nov 29, 2025

### Go Code Removal

In preparation for the new Python-based daemon and client architecture, we have removed the legacy Go codebase. This allows us to focus on a single language stack and iterate faster on the new daemon design.

**Safety Measures:**
- A backup branch was created before deletion: `wip/go-backup-20251129T115607Z`
- The deletion commit on `main` is: `45323bc`

**Removed Components:**
- `apps/qwexcloud` (Go server)
- `apps/qwexctl` (Go CLI)
- `pkg/*` (Go packages: k8s, qapi, qrunner, etc.)
- `go.mod`, `go.sum`

**Next Steps:**
- Implement the Python daemon with UDS/HTTP support.
- Refactor `qwexctl` (Python) to communicate with the daemon.
- Implement the plugin system for runners.

---

## Week 10: Dec 2, 2025

### Execution Model Finalized: Git Worktree Isolation

After discovering design flaws in the current implementation, we're documenting the correct execution model.

#### Core Invariant

**Every run executes in a git worktree, not the working directory.**

This ensures:
1. **Reproducibility**: Run tied to exact commit SHA
2. **Isolation**: Concurrent runs don't interfere
3. **Clean state**: No uncommitted changes affect execution

#### QWEX_HOME Structure

```
$QWEX_HOME/                    # ~/.qwex by default, or workspace/.qwex
  repos/                       # bare git repos (for remote storage)
    <workspace-name>.git/
  spaces/                      # ephemeral worktrees (deleted after run)
    <run-id>/
  runs/                        # persistent run metadata + logs
    <run-id>/
      run.json                 # MUST have commit field
      statuses.jsonl
      stdout.log
```

#### Run Lifecycle

```
1. User runs: qwex run python train.py

2. Pre-flight checks:
   - Is this a git repo? (required)
   - Get current commit SHA (required, stored in run.json)

3. Create worktree:
   - git worktree add --detach $QWEX_HOME/spaces/<run-id> <commit>

4. Execute in worktree:
   - cd $QWEX_HOME/spaces/<run-id>
   - python train.py > $QWEX_HOME/runs/<run-id>/stdout.log 2>&1

5. Cleanup:
   - git worktree remove $QWEX_HOME/spaces/<run-id>
   - Run metadata persists in $QWEX_HOME/runs/<run-id>/
```

#### run.json Schema (Required Fields)

```json
{
  "id": "uuid7",
  "commit": "abc123...",        // REQUIRED - for reproducibility
  "workspace_name": "my-project",
  "command": "python",
  "args": ["train.py"],
  "status": "succeeded",
  "created_at": "...",
  "started_at": "...",
  "finished_at": "..."
}
```

#### Storage Backends

Storage handles syncing code to remote execution environments.

**git-direct**: Push to bare repo via SSH
- Used with SSH layer
- Remote creates worktree from pushed commit
- `base_path` should come from layer's `qwex_home`, not hardcoded

**mount**: Direct filesystem mount
- Used with local/docker execution
- No transfer needed, worktree created locally

#### Layer + Storage Relationship

```yaml
# qwex.yaml
layers:
  ssh:
    type: ssh
    host: csc
    qwex_home: ~/.qwex        # remote QWEX_HOME

storage:
  code:
    type: git-direct
    layer: ssh                # inherits ssh_host and qwex_home from layer

runners:
  remote:
    layers: [ssh]
    storage:
      source: code            # uses git-direct storage
```

Storage config should reference layer to avoid duplication:
- `ssh_host` comes from layer
- `base_path` = `{layer.qwex_home}/repos`

#### Registry Decorators

Simplified decorator names:
- `@layer` instead of `@register_layer`
- `@storage` instead of `@register_storage`

#### Checkout a Run

To reproduce a run:
```bash
qwex checkout <run-id>
# reads run.json, gets commit, creates worktree
git worktree add ./run-<run-id> <commit>
```

#### Key Fixes Needed

1. **Run must require commit**: No run without git commit
2. **Storage depends on layer**: `git-direct` gets `ssh_host` and `base_path` from SSH layer
3. **Worktree is mandatory**: All execution happens in worktrees
4. **Shorter decorators**: `@layer`, `@storage`

---


## Week 10: Dec 3, 2025

### Template-Based Architecture: "shadcn for shell scripts"

After reflecting on the current Python-heavy implementation, we're exploring a radical simplification: **qwex as a template compiler**.

#### Core Insight

> "qwex is just a compiler that turns YAML + templates into a single executable command"

Instead of hiding layers behind Python abstractions, expose them as **user-owned shell script templates** that users can inspect, copy, and modify — like [shadcn/ui](https://ui.shadcn.com/) for shell scripts.

#### Architecture: Rigid Core + Flexible Templates

| **Core (rigid, built-in)** | **Templates (user-owned, `.qwex/templates/`)** |
|---|---|
| Run lifecycle management | SSH connection/execution |
| `run.json` generation & tracking | Docker container execution |
| Run ID generation (UUID) | Slurm job submission |
| Logging infrastructure | Singularity/Apptainer |
| `qwex list` / `qwex logs` / `qwex cancel` | Kubernetes Job templates |
| Artifact tracking (inputs/outputs) | Git worktree setup |
| Process detachment / background runs | Storage mount commands |
| Exit code capture & status | Custom wrappers (conda, nix, etc.) |
| Backend storage for run metadata | |
| Template rendering engine (Jinja) | |

#### Directory Structure

```
.qwex/
  templates/           # user-owned, inspectable shell templates
    ssh.sh.j2
    docker.sh.j2
    slurm.sh.j2
    singularity.sh.j2
    worktree.sh.j2
  targets/             # gitignored - secrets/host configs
    hpc.yaml
```

#### Template Contract

Each template:
1. Receives context variables (run ID, workspace, layer config, etc.)
2. Wraps `{{ inner }}` or `{{ command }}` 
3. Outputs valid shell

**Example `ssh.sh.j2`:**
```bash
#!/bin/bash
ssh {{ layers.ssh.user }}@{{ layers.ssh.host }} bash -c '
{{ inner | indent(2) }}
'
```

**Composition (ssh → docker):**
```bash
# Rendered for: qwex run -r hpc echo hello
ssh qtn@csc bash -c '
  docker run --rm ghcr.io/astral-sh/uv:latest bash -c '
    echo hello
  '
'
```

#### Comparison with Similar Tools

| | GitHub Workflows | Taskfile | qwex |
|---|---|---|---|
| **Focus** | CI/CD on GitHub runners | Local task runner | Remote execution anywhere |
| **Templates** | Built-in actions | None | User-owned `.j2` files |
| **Registry** | GitHub Marketplace | None | `qwex add ssh` (shadcn-style) |
| **Composition** | Steps in sequence | Task dependencies | Nested shell wrappers |

#### Design Questions (Open)

1. **Language**: Go (single binary, `text/template` stdlib) vs Python (already working, faster iteration)?
   - **Decision**: Validate in Python first, port to Go if distribution matters.

2. **GitHub Workflow syntax**: Worth inheriting for familiarity, or too heavy?
   - **Decision**: Keep `qwex run` simple. Workflows syntax is optional power feature.

3. **Overlay/patching**: Kustomize-like JSON/YAML patching?
   - **Decision**: Defer. Scope creep. Templates are enough for MVP.

#### Next Steps

1. Prove concept: Make `qwex run -r ssh echo hello` use a `.qwex/templates/ssh.sh.j2` template instead of Python code.
2. Add second layer (docker) and prove composition works.
3. Only then consider Go rewrite, registry, etc.


---

## Dec 3, 2025: Global Qwex Home Architecture

### File-Based Metadata Storage Revolution

**Problem**: JSON manipulation in bash is too limited for complex operations. Need a simpler way to store and update run metadata.

**Solution**: Replace JSON with file-based key-value storage where each metadata field is stored in its own file:

```
$HOME/.qwex/$WORKSPACE_NAME/runs/$RUN_ID/
├── meta/
│   ├── id
│   ├── command_line  
│   ├── status
│   ├── created_at
│   ├── started_at
│   ├── finished_at (optional)
│   └── exit_code (optional)
├── logs/
│   ├── stdout.log
│   └── stderr.log
```

**Benefits**:
- Bash can easily read/write individual files with `>` and `cat`
- No JSON parsing complexity
- Simple directory structure for run discovery
- Easy to extend with new metadata fields
- Atomic updates (each file is independent)

**Implementation**:
- Workspace name extracted from `qwex.yaml` `name:` field
- Global qwex home at `$HOME/.qwex/$WORKSPACE_NAME/runs/`
- File-based metadata creation and status updates
- Preserves working directory and environment

**Test Results**: Successfully tested from workspace root and deep subdirectories. Run lifecycle (create → running → succeeded/failed) works correctly with proper timestamp tracking.

---

## Dec 5, 2025: Asking questions


1. What core problem are you actually trying to solve? Beyond the surface-level features (running jobs on SSH/SLURM/Singularity, etc.), what's the fundamental pain point or inefficiency in distributed computing/ML workflows that motivated qwex? Why isn't this just a wrapper around existing tools like Kubernetes, Ray, or even plain SSH scripts? What evidence do you have that this problem is widespread enough to warrant a new tool?

> Sure. Due to the emergence of AI, machine learning models have become smaller and smarter. The foundational model became a commodity. The code, the sdk, the agentic pipeline, everything has become open-source. the last thing is that the infrastructure does not yet have a standard protocol. the research codes (public not so much, but especially private e.g. in github orgs) are notoriously difficult to reproduce. here's the data. here's the source. run it on any gpu or container or whatever you want! and that has wasted a lot of researcher's time. Moreover if the machine is shared, now you get stuck in that env and wasted idle GPU hours when it could've been used by someone else. It is a wrapper around existing tools, but it's not a wrapper of one existing tool. It's a wrapper of any tool you want to integrate. It's not even "evidence". This is a well-known, widespread problem as confirmed by my interview. Everybody has their own ways of doing things.

2. Why this modular, layered architecture (with qwml, qwp, qwexcli) instead of a monolithic or simpler design? Looking at your workspace structure, you've split things into engines, layers, commands, and models. What drove this decomposition? Is it truly necessary for extensibility, or is it premature abstraction that adds complexity without proven benefits? How do you justify the overhead of maintaining separate packages (pyproject.toml files everywhere) versus a single, cohesive codebase?

> This solves the N x M problems. It's like well you could have just pack everything into one html file. Why make react? now it makes swapping things in and out much easier. Modules should be first-class support for a programming language. (looking at you C++). Sure it could be a premature abstraction, but saying that it's a premature abstraction means there is a proof that this is a premature abstraction, then that research proving such a thing could be a great contribution. Also there is no pyproject.toml. it's just ssh.sh.j2. can you can just call qwex run. it's cohesive. I'm managing multiple files because im stupid ok?

3. What are the key trade-offs in your runner system (SSH, Docker, Singularity, etc.), and why prioritize these over cloud-native alternatives? Why not build on top of something like AWS Batch, Google Cloud Run, or even Kueue directly (since I see kueue configs in your infra)? Are you assuming on-prem or hybrid environments are the primary use case? What data or benchmarks show that your custom runners outperform or simplify compared to off-the-shelf solutions?

> Because I need a baseline to say that: as you can see cloud native integrations are much easier to do. And see the trade-off by the complexity itself. On K8S you might know you have to setup PVC? Ingress? you could have just place an agree-upon cache folder in user dir! On SSH you might see wtf k8s has kubectl secrets and it just does things for you automatically??? i had to envelope things and encrypt it. Then you can see both tradeoffs very clearly instead of doing undocumented works. Also it's not a custom runner is a runner compiler!

4. How do you handle failure modes and edge cases in job execution? From the terminal output, I see errors like "No such file or directory" and panics in Rust (uv-related). Why not design for robustness from the start—e.g., better error handling, retries, or state persistence? Is this a deliberate minimalism, or an oversight that could undermine reliability in production?

> so there are cases where it's user error. cases where you pulled a footgun on yourself. it's not minimal because it's like a port where you can plug everything in.

5. What makes qwex uniquely valuable compared to competitors like MLflow, Prefect, or Dask? Why would someone choose qwex over these established tools? What novel insights or innovations justify the effort? If it's about simplicity or integration with specific stacks (e.g., Singularity on SLURM), quantify the benefits—e.g., performance metrics, user adoption, or reduced setup time.

> You can use MLflow Prefect or Dask under qwex so that's not a good question honestly. qwex is a shell compiler. so you can just make dask.sh.j2 it's just that now the under-layer has a good starting point where you can compose things. This wasn't achievable with Makefile because there's no Makefile distro or anything like that.

6. Finally, what's your thesis's overarching narrative? How does qwex fit into the broader story of distributed systems or ML engineering? Are you claiming it's a paradigm shift, or just an incremental improvement? What risks are you downplaying, and how will you defend against criticisms that this is "yet another orchestration tool" with unclear differentiation?

> It's a paradigm shift. because now it fills the gap between the last layer of knowledge sharing in ML space: executing the code. Everything else is shared but not this specific part.

## Reflection Log: Why This Design, Not Another Way

### Overview
This reflection log synthesizes the design rationale for Qwex (Queued Workspace-Aware EXecutor) based on critical questioning and self-examination. As a thesis foundation, it addresses why certain architectural choices were made, trade-offs considered, and alternatives rejected. The analysis draws from interviews (N=15 with ML engineers, students, and professors), project evolution, and ongoing development challenges. Critically, Qwex positions itself as a "paradigm shift" in ML infrastructure by filling the execution gap in knowledge sharing, but this claim remains unproven without empirical data.

### Core Problem and Motivation
**Why this problem?** The emergence of AI/ML commoditization has made models, code, SDKs, and pipelines open-source, but infrastructure lacks standardized protocols. Research code (especially private) is notoriously hard to reproduce: "here's the data, run it on any GPU/container!" wastes researchers' time and GPU resources. Interviews revealed diverse pain points—burning money on idle VMs, ad-hoc spreadsheets for reservations, overnight runs on personal PCs—highlighting socio-economic barriers to standardization adoption. Qwex isn't a wrapper for one tool but a "standard-gatherer" for any integrable tool, allowing users to compose solutions without imposing new standards.

**Why not alternatives?** Pushing for universal protocols (e.g., a job spec standard) was rejected due to adoption inertia. Existing tools (K8s, Ray) solve parts but not composition across heterogeneous environments. Qwex acts as "protective gear" over "hot lava," enabling reproducibility without waiting for ecosystem consensus.

**Critical doubt:** Without quantitative metrics (e.g., time waste quantification), this is anecdotal. The thesis risks being dismissed as solving a "first-world problem" in academia.

### Architecture and Modularity
**Why modular (qwml, qwp, qwexcli)?** To solve "N x M problems"—combinatorial explosions from multiple runtimes (N) and backends (M). Analogous to React's component modularity vs. monolithic HTML: swapping layers (e.g., engines, layers, commands) is easier. Modules are "first-class" like in programming languages (unlike C++'s lack thereof). Fragmentation (multiple pyproject.toml files) stems from iterative pivots, not design intent—admitted as "stupidity" in managing files.

**Why not monolithic or DSL?** Monolithic would limit extensibility. A DSL was avoided to prevent "yet another standard," aligning with the anti-standard ethos. Instead, shell templates (e.g., ssh.sh.j2) provide cohesion: "just call qwex run."

**Critical doubt:** Modularity may be premature without proof of N x M benefits. Fragmentation indicates instability; if unaddressed, it undermines maintainability. Evidence needed: user studies showing modularity reduces complexity.

### Runner System and Trade-Offs
**Why runners as a "compiler," not custom?** Provides a baseline for comparing trade-offs: cloud-native ease vs. on-prem simplicity (e.g., K8s PVCs/ingress vs. user-dir cache). Shows complexities clearly (e.g., SSH envelope encryption vs. K8s secrets). Not custom runners but a compiler generating execution scripts.

**Why prioritize SSH/SLURM/Singularity over cloud-only?** Interviews showed hybrid/on-prem needs. Cloud tools (AWS Batch) are easier but obscure trade-offs; Qwex makes them explicit.

**Critical doubt:** No benchmarks yet (project 50% done). Claims of "much easier" integrations are speculative. Evaluation via Olsen's HCI criteria is promising but unapplied—how will it validate effectiveness?

### Failure Modes and Robustness
**Why minimal error handling?** Assumes user errors ("footguns") are inevitable; Qwex is a "port" for plugging in, not a safety net. Only bugs in compilation are "real" errors. Deferred for later.

**Why not prioritize robustness?** Focus on MVP execution over perfection.

**Critical doubt:** Logs show file-not-found and Rust panics—unacceptable for production. Skipping this weakens the thesis; robustness is key for reproducibility claims.

### Uniqueness and Competitors
**Why composable over wrappers?** Users have different requirements (e.g., Ray migration pains); keeping runtime outside code avoids lock-in. Shell compiler enables composition (e.g., dask.sh.j2) beyond Makefiles' limitations. Integrates MLflow/Prefect/Dask without replacing them.

**Why not use existing tools directly?** They don't compose across backends or isolate runtimes.

**Critical doubt:** If Makefiles can do similar with plugins, what's the unique value? Examples needed to prove superiority.

### Overarching Narrative and Risks
**Why a "paradigm shift"?** Fills the "last layer" of ML sharing: executing code. Weights & Biases tracks experiments assuming code runs; GitHub Actions handles CI/CD. Qwex enables reproducible execution across infrastructures.

**Risks downplayed:** Abandonment (biggest fear)—mitigated by pivoting (e.g., from prototype 1). No Plan B beyond "think of a way to pivot." Project incompleteness (50% done, no data) risks thesis failure.

**Critical doubt:** "Paradigm shift" is bold without adoption evidence. If abandoned, the thesis becomes a cautionary tale of overambition. Pivot to studying socio-economic factors instead?

### Lessons and Thesis Implications
This design reflects pragmatism over perfection: build what works for users, avoid standards wars. But critical gaps (data, robustness, stability) must be addressed. For the thesis, emphasize iterative design, user-centered insights, and the "standard-gatherer" metaphor. Future work: complete evaluation, stabilize architecture, gather metrics. If Qwex succeeds, it validates the approach; if not, it highlights infrastructure standardization's challenges.


## Week 10: Dec 7, 2025

- Added a minimal plugin scaffold and project scaffolding improvements for the CLI package `apps/qwexcli`:
  - `apps/qwexcli/qwexcli/plugins/base.py`: simple plugin exposing `run(argv)` which executes a command.
  - `apps/qwexcli/qwexcli/lib/project.py`: scaffold now writes explicit `defaults` and `runners` into `.qwex/config.yaml` and creates `.qwex/.gitignore` to ignore internal artifacts.
  - `apps/qwexcli/qwexcli/lib/config.py`: removed `workspaces` from the schema; added `defaults` and `runners` fields (defaults.runner -> "base", runners.base.plugins -> ["base"]).
  - Tests updated to assert the new defaults and the presence of `.qwex/.gitignore`.
