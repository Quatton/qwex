# ROAM Controller

FastAPI-based job submission and management API for Kubernetes + Kueue.

## Development

### Prerequisites
- Python 3.12+
- Access to a Kubernetes cluster with Kueue installed
- kubectl configured

### Setup

```bash
# Install dependencies
uv sync

# For dev: run kubectl proxy in a separate terminal
kubectl proxy --port=8001

# Run the controller (automatically uses proxy on localhost:8001)
K8S_PROXY=http://127.0.0.1:8001 fastapi dev src/controller/main.py
```

The controller automatically detects your environment:
- **Dev**: Set `K8S_PROXY` to use kubectl proxy (no auth needed)
- **Prod**: Runs in-cluster with ServiceAccount (deployed in Kubernetes)

### RBAC

The controller requires a ServiceAccount with permissions to manage Kueue Workloads.
See `infra/controller/` for RBAC manifests.

## 🎯 **Purpose**

The Controller is the core API server that:
- Accepts job submissions via REST API
- Translates requests to Kubernetes Job + Kueue resources
- Manages job lifecycle (submit, monitor, cancel)
- Provides job logs and status information
- Generates OpenAPI spec for client generation

## 📋 **Implementation Status**

### ✅ **Completed**
- [x] Basic Python project structure
- [x] UV dependency management configuration

### 🚧 **In Progress**
- [ ] FastAPI application setup
- [ ] Pydantic models for job specifications
- [ ] Kubernetes client integration

### 📅 **Planned**

#### Core API Endpoints
```http
POST   /api/v1/jobs              # Submit new job
GET    /api/v1/jobs              # List jobs (with filtering)
GET    /api/v1/jobs/{id}         # Get job details
DELETE /api/v1/jobs/{id}         # Cancel job
GET    /api/v1/jobs/{id}/logs    # Stream job logs
GET    /api/v1/jobs/{id}/status  # Get job status
```

#### Advanced Features
- [ ] **Job Templates** - Predefined configurations
- [ ] **Batch Operations** - Submit multiple jobs
- [ ] **Resource Validation** - Check cluster capacity
- [ ] **User Management** - RBAC integration
- [ ] **Metrics Export** - Prometheus metrics

## 🏗️ **Architecture**

```
┌─────────────────┐
│   FastAPI App   │
├─────────────────┤
│   API Routes    │ ── /api/v1/jobs/*
├─────────────────┤
│  Job Service    │ ── Business logic
├─────────────────┤
│ Kubernetes      │ ── K8s client
│ Client          │    + Kueue APIs
└─────────────────┘
```

## 📝 **API Models**

### Job Specification (Planned)
```python
class JobSpec(BaseModel):
    name: Optional[str] = None
    image: str
    command: List[str]
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    resources: Resources
    queue: str = "user-queue"
    labels: Optional[Dict[str, str]] = None

class Resources(BaseModel):
    cpu: str = "100m"
    memory: str = "128Mi"
    gpu: Optional[int] = None

class JobResponse(BaseModel):
    id: str
    status: JobStatus
    spec: JobSpec
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
```

### Job Status
```python
class JobStatus(str, Enum):
    PENDING = "pending"      # Queued in Kueue
    RUNNING = "running"      # Pod executing
    SUCCEEDED = "succeeded"  # Completed successfully
    FAILED = "failed"        # Failed with error
    CANCELLED = "cancelled"  # User cancelled
```

## 🚀 **Development**

### Setup
```bash
cd apps/controller
uv sync
```

### Run Development Server
```bash
uv run fastapi dev src/main.py --host 0.0.0.0 --port 8000 --reload
```

### Generate OpenAPI Client
```bash
# Start the server first, then:
curl http://localhost:8000/openapi.json > openapi.json
```

### Testing
```bash
# Unit tests
uv run pytest tests/

# Integration tests (requires cluster access)
uv run pytest tests/integration/
```

## 🐳 **Container Deployment**

### Multi-stage Dockerfile (Planned)
```dockerfile
FROM python:3.12-slim as builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
ENV PATH="/app/.venv/bin:$PATH"
CMD ["fastapi", "run", "src/main.py", "--host", "0.0.0.0"]
```

### Kubernetes Deployment
```yaml
# Deploy as a pod in the k3s cluster
apiVersion: apps/v1
kind: Deployment
metadata:
  name: roam-controller
spec:
  replicas: 2
  selector:
    matchLabels:
      app: roam-controller
  template:
    spec:
      containers:
      - name: controller
        image: roam/controller:latest
        ports:
        - containerPort: 8000
        env:
        - name: KUBERNETES_SERVICE_HOST
          value: "kubernetes.default.svc"
```

## 🔧 **Configuration**

### Environment Variables
```bash
# Kubernetes configuration
KUBECONFIG=/path/to/kubeconfig        # If running outside cluster
KUBERNETES_NAMESPACE=default         # Default namespace for jobs

# API configuration
ROAM_HOST=0.0.0.0                    # Server bind address
ROAM_PORT=8000                       # Server port
ROAM_LOG_LEVEL=info                  # Logging level

# Kueue configuration
DEFAULT_QUEUE=user-queue             # Default queue name
MAX_JOBS_PER_USER=10                 # Rate limiting
```

## 📊 **Monitoring**

### Health Checks
```http
GET /health        # Basic health check
GET /health/ready  # Readiness probe (K8s connectivity)
GET /health/live   # Liveness probe
```

### Metrics (Planned)
- Job submission rate
- Job completion time
- Queue depth
- API response times
- Error rates

## 🔗 **Integration**

### With CLI
```python
# Generated client usage
from roam_client import JobsAPI

client = JobsAPI(base_url="http://controller.local:8000")
job = await client.submit_job(
    image="python:3.12",
    command=["python", "-c", "print('hello world')"],
    resources={"cpu": "100m", "memory": "128Mi"}
)
```

### With Kubernetes
- Uses `kubernetes-asyncio` client
- ServiceAccount with appropriate RBAC
- Watches Job and Pod events
- Integrates with Kueue CRDs
