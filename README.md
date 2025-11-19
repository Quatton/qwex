# QWEX - Queue-based Workload EXecution

A distributed job execution platform built on Kubernetes and Kueue, designed for running workloads across multiple machines with seamless cross-machine networking via Tailscale.

## 🚢 **Production Deployment**

When deploying the controller to a real cluster, you should use Kubernetes Secrets for sensitive credentials like the GitHub App Private Key.

### Secrets Setup

Create a secret named `qwex-controller-secrets`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: qwex-controller-secrets
type: Opaque
stringData:
  GITHUB_APP_ID: "123456"
  GITHUB_APP_PRIVATE_KEY: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
    -----END RSA PRIVATE KEY-----
  AUTH_SECRET: "your-32-char-secret"
```

Then map these secrets to environment variables in your Deployment manifest:

```yaml
env:
  - name: GITHUB_APP_PRIVATE_KEY
    valueFrom:
      secretKeyRef:
        name: qwex-controller-secrets
        key: GITHUB_APP_PRIVATE_KEY
  # ... map other vars
```
