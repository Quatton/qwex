# QWP - Qwex Protocol SDK

A Python SDK for ML run orchestration following the Qwex Protocol.

## Installation

```bash
pip install qwp
```

## Quick Start

```python
import asyncio
from qwp import LocalRunner, JobSpec

async def main():
    runner = LocalRunner()
    
    # Create a job spec
    job_spec = JobSpec(
        command="python",
        args=["train.py", "--epochs", "10"],
        env={"CUDA_VISIBLE_DEVICES": "0"},
    )
    
    # Submit the job
    run = await runner.submit(job_spec, name="training-run")
    print(f"Started run: {run.id}")
    
    # Follow logs
    async for line in runner.logs(run.id, follow=True):
        print(line)
    
    # Get final status
    run = await runner.get_run(run.id)
    print(f"Finished with status: {run.status}")

asyncio.run(main())
```

## Features

- **Local execution**: Run jobs on your local machine
- **Detach/attach**: Start a job and reattach later
- **Persistent state**: Run state stored in `.qwex/runs/`
- **Log streaming**: Follow logs in real-time

## License

MIT
