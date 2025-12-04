# qwml - Qwex Markup Language

Composable shell layer compiler. "React for shell scripts."

## Architecture

A **Stack** is a tuple of 4 layers (the "4 A's"):

```
Stack = (Access, Allocation, Arena, Agent)
         L1       L2          L3      L4
```

Each layer is a shell script that wraps the next layer via `"$@"`.

### Data Flows

- **Source**: L1 push → L4 pull
- **Files In**: L2 mount → L3 bind  
- **Files Out**: L4 push → L1 pull

### The Noop Layer

Any layer can be a **noop** (identity function):

```bash
set -euo pipefail
exec "$@"
```

This means `Stack(noop, noop, noop, agent)` compiles to just the agent script.

## Usage

```python
from qwml import compile_stack, noop

# All noops = just runs the command
script = compile_stack(
    access=noop(),
    allocation=noop(), 
    arena=noop(),
    agent=noop(),
    command=["python", "hello.py"]
)
```

## Layer Examples

- **Access (L1)**: SSH, kubectl exec, localhost
- **Allocation (L2)**: Slurm sbatch, K8s Job spec, AWS Batch
- **Arena (L3)**: Docker, Singularity, Apptainer, Conda
- **Agent (L4)**: qwex-agent, custom wrapper
