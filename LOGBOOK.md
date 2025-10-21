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