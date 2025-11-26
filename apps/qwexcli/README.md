# Qwex CLI

Command-line interface for Qwex Protocol.

## Installation

```bash
pip install qwexcli
```

## Usage

### Run a command

```bash
# Run and follow logs
qwex run python train.py

# Run with arguments
qwex run python train.py --epochs 10 --lr 0.001

# Run with a name
qwex run --name "experiment-1" python train.py

# Run detached (don't follow logs)
qwex run --detach python long_running.py

# Run with environment variables
qwex run --env CUDA_VISIBLE_DEVICES=0 python train.py
```

### Manage runs

```bash
# List active runs
qwex list

# List all runs (including finished)
qwex list --all

# Check status of a run
qwex status <run-id>

# Attach to a running job
qwex attach <run-id>

# Cancel a run
qwex cancel <run-id>

# View logs
qwex logs <run-id>
qwex logs --follow <run-id>

# Clean up finished runs
qwex clean
```

## How it works

- Jobs run as detached subprocesses
- Logs are streamed to `.qwex/runs/<run-id>/stdout.log`
- Run state is persisted in `.qwex/runs/<run-id>/run.json`
- Ctrl+C during `run` or `attach` detaches without killing the job

## License

MIT
