## kueue-hello-world — Quick start

This example shows a minimal setup for Kueue using the manifests in this directory:

- `resource-flavor.yaml` — defines a ResourceFlavor used by the ClusterQueue.
- `cluster-queue.yaml` — a ClusterQueue with nominal quotas for CPU and memory.
- `local-queue.yaml` — a LocalQueue that points to the ClusterQueue.
- `job.yaml` — a suspended `batch/v1` Job labeled so Kueue will create a Workload for it.
- `kustomization.yaml` — groups the above manifests for convenience.

## Prerequisites

- A Kubernetes cluster (kind/k3d/minikube, or a real cluster).
- The Kueue CRDs and controller must be installed in the cluster so the `kueue.x-k8s.io` API group is available.
- `kubectl` configured to talk to the target cluster.

If Kueue is not installed, follow the upstream project instructions to install its controller and CRDs first.

## Apply the example

From this directory (`examples/kueue-hello-world`) you can apply everything using kustomize via `kubectl`:

```bash
# apply all example resources (uses the bundled kustomization.yaml)
kubectl apply -k .
```

This creates the `ResourceFlavor`, `ClusterQueue`, `LocalQueue`, and the suspended `Job` named `sample-job` in the `default` namespace (the `kustomization.yaml` sets `namespace: default`).

If you prefer to apply individual files, run:

```bash
kubectl apply -f resource-flavor.yaml
kubectl apply -f cluster-queue.yaml
kubectl apply -f local-queue.yaml
kubectl apply -f job.yaml
```

## Verify resources

Check that the Kueue resources were created:

```bash
kubectl get resourceflavors
kubectl get clusterqueues
kubectl get localqueues
```

Check the Job and any Workload that the Kueue controller may create (Workloads are created by the controller when it observes the Job):

```bash
kubectl get jobs -n default
# If the Workload CRD is installed, list workloads (group/version may vary):
kubectl get workloads -A || true
```

You can also describe resources to get more details and events:

```bash
kubectl describe clusterqueue cluster-queue
kubectl describe localqueue user-queue
kubectl describe job sample-job -n default
```

## Run the Job (resume)

The `job.yaml` is created with `spec.suspend: true` so the Job won't start until you resume it. To let the Job run, unset the suspend flag:

```bash
kubectl patch job sample-job -n default --type='merge' -p '{"spec":{"suspend":false}}'
```

After resuming, the Kueue controller should admit and create pods for the Job according to the ClusterQueue's quotas. Watch the Job and pods:

```bash
kubectl get job sample-job -n default -w
kubectl get pods -n default -l job-name=sample-job -w
```

Get logs from the Job pod when it starts:

```bash
# find the pod name
POD=$(kubectl get pods -n default -l job-name=sample-job -o jsonpath='{.items[0].metadata.name}')
kubectl logs -n default "$POD"
```

If Kueue created a Workload resource you can inspect it for admission/allocation decisions from the controller:

```bash
kubectl describe workload <workload-name> -n <namespace>
# or if the Workload CRD is cluster-scoped / different group: kubectl get workloads -A
```

## Cleanup

To remove the example resources:

```bash
kubectl delete -k .
# or delete the files individually
kubectl delete -f job.yaml -f local-queue.yaml -f cluster-queue.yaml -f resource-flavor.yaml
```

## Troubleshooting notes

- If `kubectl get` for the `kueue.x-k8s.io` resources fails, ensure the Kueue CRDs are installed and that your `kubectl` context points to the intended cluster.
- If the Job never gets pods after resuming, check `kubectl describe workload` (if present) and `kubectl describe clusterqueue cluster-queue` to see quota usage and events.
- Use `kubectl logs` on the Kueue controller (if you installed it in the cluster) to inspect controller-side errors.

## What this example demonstrates

This example demonstrates how a Job submitted to a Kueue-managed queue can be admitted and scheduled according to cluster-level resource flavors and quotas. It is intentionally minimal so you can experiment by changing resource requests, clusterQueue quotas, or by installing additional flavors.

---
If you'd like, I can also add a short script to apply and resume automatically, or expand the README with expected sample outputs. Tell me which you'd prefer.
