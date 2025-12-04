"""Example: Generate compiled scripts for different stacks.

Demonstrates the template-based layer system.
"""

from qwml import compile_stack, template, inline


# Helper: create a noop layer from template
def noop():
    return template("noop.sh.j2", name="noop")


# Helper: create an agent layer from template
def agent(**props):
    return template("agent.sh.j2", props=props, name="agent")


# 1. All noops - simplest possible stack
print("=" * 60)
print("STACK 1: All Noops (identity)")
print("=" * 60)
script = compile_stack(noop(), noop(), noop(), noop())
print(script)

# 2. Local with agent - runs command locally with logging
print("=" * 60)
print("STACK 2: Local with Agent")
print("=" * 60)
script = compile_stack(
    access=noop(),
    allocation=noop(),
    arena=noop(),
    agent=agent(qwex_home="~/.qwex", run_id="local-001"),
)
print(script)

# 3. SSH + bare metal (using inline for custom script)
print("=" * 60)
print("STACK 3: SSH (inline script)")
print("=" * 60)
script = compile_stack(
    access=inline(
        """# L1: SSH to remote
ssh user@remote "$@" """,
        name="ssh",
    ),
    allocation=noop(),
    arena=noop(),
    agent=agent(run_id="ssh-001"),
)
print(script)

# 4. Full stack using templates: SSH + Slurm + Singularity
print("=" * 60)
print("STACK 4: SSH + Slurm + Singularity + Agent (all templates)")
print("=" * 60)
script = compile_stack(
    access=template(
        "ssh.sh.j2", props={"host": "cluster.example.com", "user": "researcher"}
    ),
    allocation=template(
        "slurm.sh.j2", props={"gpus": 1, "time": "01:00:00", "partition": "gpu"}
    ),
    arena=template("singularity.sh.j2", props={"image": "pytorch.sif", "nv": True}),
    agent=agent(qwex_home="~/.qwex", run_id="gpu-train-001", stream_output=True),
)
print(script)
