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