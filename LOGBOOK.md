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