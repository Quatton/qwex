import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from kubernetes import client
from kubernetes.client.rest import ApiException

from controller.config import kube


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    kube.setup()
    yield
    # Shutdown (nothing to do for now)


app = FastAPI(lifespan=lifespan)


async def stream_job_logs_sse() -> AsyncGenerator[str, None]:
    """Create a job, wait for it to run, and stream its logs as SSE."""
    batch_v1 = client.BatchV1Api()
    core_v1 = client.CoreV1Api()
    
    # Generate a unique job name
    job_name = f"demo-job-{int(time.time())}"
    namespace = "default"
    
    def sse_format(data: str) -> str:
        """Format data as Server-Sent Event."""
        return f"data: {data}\n\n"
    
    # Define the job (similar to job.yaml but in Python)
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(
            name=job_name,
            labels={"kueue.x-k8s.io/queue-name": "user-queue"}
        ),
        spec=client.V1JobSpec(
            parallelism=1,
            completions=1,
            suspend=True,
            template=client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="main",
                            image="ghcr.io/astral-sh/uv:debian",
                            image_pull_policy="IfNotPresent",
                            command=["/bin/sh", "-c"],
                            args=[
                                "set -e\n"
                                "uv venv\n"
                                ". .venv/bin/activate\n"
                                "uv pip install numpy\n"
                                "echo 'Running python script...'\n"
                                "python -c \"import numpy as np; print('Numpy version:', np.__version__); print('Random number:', np.random.rand(3))\"\n"
                                "uname -a\n"
                                "echo 'Job completed successfully.'"
                            ],
                            resources=client.V1ResourceRequirements(
                                requests={"cpu": "100m", "memory": "128Mi"}
                            )
                        )
                    ]
                )
            )
        )
    )
    
    try:
        # Create the job
        yield sse_format(f"Creating job '{job_name}'...")
        batch_v1.create_namespaced_job(namespace=namespace, body=job)
        yield sse_format("Job created successfully!")
        yield sse_format("")
        
        # Wait for pod to be created
        yield sse_format("Waiting for pod to be created...")
        pod_name = None
        for i in range(60):  # Wait up to 60 seconds
            await asyncio.sleep(1)
            pods = core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"job-name={job_name}"
            )
            if pods.items:
                pod_name = pods.items[0].metadata.name
                yield sse_format(f"Pod '{pod_name}' found!")
                yield sse_format("")
                break
        
        if not pod_name:
            yield sse_format("Error: Pod was not created in time")
            return
        
        # Wait for pod to start running
        yield sse_format("Waiting for pod to start...")
        for i in range(120):  # Wait up to 2 minutes
            await asyncio.sleep(2)
            pod_resp: client.V1Pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)  # type: ignore
            if pod_resp.status and pod_resp.status.phase:
                phase = pod_resp.status.phase
                yield sse_format(f"Pod status: {phase}")
                
                if phase in ["Running", "Succeeded", "Failed"]:
                    break
        
        yield sse_format("")
        yield sse_format("--- Job Logs ---")
        
        # Stream logs
        try:
            # Try to get logs - this will work once the container starts
            for attempt in range(30):  # Try for 30 seconds
                try:
                    log_stream = core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        follow=True,
                        _preload_content=False
                    )
                    
                    for line in log_stream:
                        yield sse_format(line.decode('utf-8').rstrip())
                    break
                except ApiException as e:
                    if attempt < 29:
                        await asyncio.sleep(1)
                        yield sse_format(".")
                    else:
                        yield sse_format(f"Error getting logs: {e}")
                        
        except Exception as e:
            yield sse_format(f"Error streaming logs: {e}")
        
        yield sse_format("")
        yield sse_format("--- Job Complete ---")
        
    except Exception as e:
        yield sse_format(f"Error: {e}")
    finally:
        # Optional cleanup - uncomment if you want to delete the job after
        # try:
        #     batch_v1.delete_namespaced_job(
        #         name=job_name,
        #         namespace=namespace,
        #         propagation_policy='Foreground'
        #     )
        #     yield f"\nJob '{job_name}' deleted.\n"
        # except:
        #     pass
        pass


@app.get("/")
async def read_root():
    """Create a demo job and stream its output using Server-Sent Events."""
    return StreamingResponse(
        stream_job_logs_sse(),
        media_type="text/event-stream"
    )
