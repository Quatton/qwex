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
  
### Activities

- Add RBAC manifests for the controller to manage kueue workloads.
  > Since this RBAC manifests only live in side the 