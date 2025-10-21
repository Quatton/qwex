# QWEX CLI

Command-line interface for submitting and managing jobs on the QWEX platform.

## 🎯 **Purpose**

The CLI provides a user-friendly command-line interface for:
- Submitting jobs to the QWEX cluster
- Monitoring job status and logs
- Managing job lifecycle (cancel, retry)
- Configuring API endpoints and authentication

## 📋 **Implementation Status**

### ✅ **Completed**
- [x] Project directory created

### 🚧 **In Progress**
- [ ] OpenAPI client generation setup
- [ ] Click-based CLI framework
- [ ] Configuration management

### 📅 **Planned Features**

#### Core Commands
```bash
# Job Management
qwex submit <job-spec>              # Submit a new job
qwex status <job-id>                # Get job status
qwex logs <job-id> [--follow]       # View job logs
qwex cancel <job-id>                # Cancel running job
qwex list [--status=running]        # List jobs with filters

# Configuration
qwex config set endpoint <url>      # Set API endpoint
qwex config set token <token>       # Set auth token
qwex config show                    # Show current config

# Templates
qwex template list                  # List available templates
qwex template show <name>           # Show template details
qwex submit --template <name>       # Submit using template
```

#### Advanced Commands
```bash
# Batch Operations
qwex submit --batch jobs/*.yaml     # Submit multiple jobs
qwex cancel --all --status=pending  # Cancel all pending jobs

# Interactive Mode
qwex shell                          # Start interactive session

# Job Specifications
qwex spec validate <file>           # Validate job spec
qwex spec generate --image python:3.12 --command "python script.py"
```

## 🏗️ **Architecture**

```
┌─────────────────┐
│   Click CLI     │ ── Command definitions
├─────────────────┤
│  Generated      │ ── Auto-generated from
│  Client         │    FastAPI OpenAPI spec
├─────────────────┤
│  Configuration  │ ── Config file management
│  Manager        │    (~/.qwex/config.yaml)
├─────────────────┤
│  Output         │ ── Pretty printing,
│  Formatter      │    tables, progress bars
└─────────────────┘
```

## 📦 **Installation** (Planned)

### From PyPI
```bash
pip install qwex-cli
```

### From Source
```bash
cd apps/cli
uv sync
uv run qwex --help
```

### As Standalone Binary
```bash
# Using PyInstaller
uv run pyinstaller --onefile src/qwex_cli/main.py
```

## 🚀 **Usage Examples**

### Basic Job Submission
```bash
# Simple Python job
qwex submit --image python:3.12 --command "python -c 'print(\"Hello QWEX!\")'"

# With resource requirements
qwex submit \
  --image pytorch/pytorch:latest \
  --command "python train.py" \
  --cpu 2 \
  --memory 4Gi \
  --gpu 1

# From YAML specification
qwex submit job-spec.yaml
```

### Job Monitoring
```bash
# Check status
qwex status job-abc123

# Follow logs in real-time
qwex logs job-abc123 --follow

# List all jobs
qwex list

# Filter jobs
qwex list --status running --queue gpu-queue
```

### Configuration
```bash
# Set API endpoint
qwex config set endpoint https://qwex.example.com

# Show configuration
qwex config show
```

## 📝 **Job Specification Format**

### YAML Format
```yaml
# job-spec.yaml
apiVersion: qwex.dev/v1
kind: Job
metadata:
  name: my-training-job
  labels:
    project: ml-experiments
spec:
  image: pytorch/pytorch:2.0
  command: ["python", "train.py"]
  args: ["--epochs", "100", "--lr", "0.001"]
  env:
    CUDA_VISIBLE_DEVICES: "0"
  resources:
    cpu: 4
    memory: 8Gi
    gpu: 1
  queue: gpu-queue
  volumes:
    - name: dataset
      hostPath: /data/imagenet
      mountPath: /workspace/data
```

### CLI Flags to YAML Mapping
```bash
qwex submit \
  --image pytorch/pytorch:2.0 \
  --command "python train.py" \
  --args "--epochs 100" \
  --env CUDA_VISIBLE_DEVICES=0 \
  --cpu 4 \
  --memory 8Gi \
  --gpu 1 \
  --queue gpu-queue
```

## 🔧 **Configuration**

### Config File Location
```
~/.qwex/config.yaml
```

### Config Format
```yaml
# ~/.qwex/config.yaml
api:
  endpoint: https://qwex-api.example.com
  timeout: 30
  retry_count: 3

auth:
  token: eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...

output:
  format: table  # table, json, yaml
  color: true
  verbose: false

defaults:
  queue: user-queue
  resources:
    cpu: 100m
    memory: 128Mi
```

### Environment Variables
```bash
export QWEX_ENDPOINT=https://qwex-api.example.com
export QWEX_TOKEN=your-auth-token
export QWEX_CONFIG_DIR=~/.config/qwex
```

## 📊 **Output Formats**

### Table Format (Default)
```
JOB ID      STATUS     QUEUE       IMAGE           CREATED
job-abc123  Running    user-queue  python:3.12     2m ago
job-def456  Pending    gpu-queue   pytorch:latest  5m ago
job-ghi789  Complete   user-queue  ubuntu:22.04    1h ago
```

### JSON Format
```json
{
  "jobs": [
    {
      "id": "job-abc123",
      "status": "running",
      "queue": "user-queue",
      "image": "python:3.12",
      "created_at": "2025-10-16T10:30:00Z"
    }
  ]
}
```

## 🎨 **User Experience Features**

### Progress Indicators
```bash
qwex submit job.yaml
✓ Validating job specification
✓ Submitting to queue: user-queue  
⏳ Job queued: job-abc123
✓ Job started running
```

### Interactive Job Selection
```bash
qwex logs
? Select a job to view logs:
❯ job-abc123 (Running)  - Python training script
  job-def456 (Pending)  - Data processing job  
  job-ghi789 (Complete) - Model evaluation
```

### Auto-completion
```bash
# Bash completion
qwex submit --image <TAB>
# Shows: python:3.12, pytorch/pytorch:latest, ubuntu:22.04, ...

qwex status <TAB>
# Shows: job-abc123, job-def456, job-ghi789, ...
```

## 🧪 **Testing**

### Unit Tests
```bash
cd apps/cli
uv run pytest tests/unit/
```

### Integration Tests
```bash
# Requires running QWEX API
uv run pytest tests/integration/ --api-endpoint http://localhost:8000
```

### CLI Testing with Typer
```python
from typer.testing import CliRunner
from qwex_cli.main import app

def test_submit_command():
    runner = CliRunner()
    result = runner.invoke(app, ["submit", "--image", "python:3.12"])
    assert result.exit_code == 0
```

## 🔌 **Client Generation**

### From OpenAPI Spec
```bash
# Generate Python client from running API
curl http://localhost:8000/openapi.json > openapi.json
openapi-generator-cli generate \
  -i openapi.json \
  -g python \
  -o generated/qwex-client
```

### Auto-regeneration
```bash
# Watch API for changes and regenerate
qwex dev --watch-api --regenerate-client
```