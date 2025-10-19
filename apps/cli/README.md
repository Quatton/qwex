# ROAM CLI

Command-line interface for submitting and managing jobs on the ROAM platform.

## 🎯 **Purpose**

The CLI provides a user-friendly command-line interface for:
- Submitting jobs to the ROAM cluster
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
roam submit <job-spec>              # Submit a new job
roam status <job-id>                # Get job status
roam logs <job-id> [--follow]       # View job logs
roam cancel <job-id>                # Cancel running job
roam list [--status=running]        # List jobs with filters

# Configuration
roam config set endpoint <url>      # Set API endpoint
roam config set token <token>       # Set auth token
roam config show                    # Show current config

# Templates
roam template list                  # List available templates
roam template show <name>           # Show template details
roam submit --template <name>       # Submit using template
```

#### Advanced Commands
```bash
# Batch Operations
roam submit --batch jobs/*.yaml     # Submit multiple jobs
roam cancel --all --status=pending  # Cancel all pending jobs

# Interactive Mode
roam shell                          # Start interactive session

# Job Specifications
roam spec validate <file>           # Validate job spec
roam spec generate --image python:3.12 --command "python script.py"
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
│  Manager        │    (~/.roam/config.yaml)
├─────────────────┤
│  Output         │ ── Pretty printing,
│  Formatter      │    tables, progress bars
└─────────────────┘
```

## 📦 **Installation** (Planned)

### From PyPI
```bash
pip install roam-cli
```

### From Source
```bash
cd apps/cli
uv sync
uv run roam --help
```

### As Standalone Binary
```bash
# Using PyInstaller
uv run pyinstaller --onefile src/roam_cli/main.py
```

## 🚀 **Usage Examples**

### Basic Job Submission
```bash
# Simple Python job
roam submit --image python:3.12 --command "python -c 'print(\"Hello ROAM!\")'"

# With resource requirements
roam submit \
  --image pytorch/pytorch:latest \
  --command "python train.py" \
  --cpu 2 \
  --memory 4Gi \
  --gpu 1

# From YAML specification
roam submit job-spec.yaml
```

### Job Monitoring
```bash
# Check status
roam status job-abc123

# Follow logs in real-time
roam logs job-abc123 --follow

# List all jobs
roam list

# Filter jobs
roam list --status running --queue gpu-queue
```

### Configuration
```bash
# Set API endpoint
roam config set endpoint https://roam.example.com

# Show configuration
roam config show
```

## 📝 **Job Specification Format**

### YAML Format
```yaml
# job-spec.yaml
apiVersion: roam.dev/v1
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
roam submit \
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
~/.roam/config.yaml
```

### Config Format
```yaml
# ~/.roam/config.yaml
api:
  endpoint: https://roam-api.example.com
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
export ROAM_ENDPOINT=https://roam-api.example.com
export ROAM_TOKEN=your-auth-token
export ROAM_CONFIG_DIR=~/.config/roam
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
roam submit job.yaml
✓ Validating job specification
✓ Submitting to queue: user-queue  
⏳ Job queued: job-abc123
✓ Job started running
```

### Interactive Job Selection
```bash
roam logs
? Select a job to view logs:
❯ job-abc123 (Running)  - Python training script
  job-def456 (Pending)  - Data processing job  
  job-ghi789 (Complete) - Model evaluation
```

### Auto-completion
```bash
# Bash completion
roam submit --image <TAB>
# Shows: python:3.12, pytorch/pytorch:latest, ubuntu:22.04, ...

roam status <TAB>
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
# Requires running ROAM API
uv run pytest tests/integration/ --api-endpoint http://localhost:8000
```

### CLI Testing with Typer
```python
from typer.testing import CliRunner
from roam_cli.main import app

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
  -o generated/roam-client
```

### Auto-regeneration
```bash
# Watch API for changes and regenerate
roam dev --watch-api --regenerate-client
```