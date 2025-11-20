# Qwex Configuration

Qwex uses a two-tier configuration system similar to Fly.io, Vercel, and other modern tools.

## Configuration Files

### `qwex.yaml` (Project Config - TRACKED)

This file lives in your project root and should be **committed to git**. It defines project-wide settings that are shared with your team.

```yaml
# qwex.yaml
artifacts:
  watch_directories:
    - out
    - models
  ignore_patterns:
    - "*.tmp"
    - "*.log"
  max_file_size_mb: 1000

jobs:
  train:
    command: python
    args: [train.py]
    env:
      CUDA_VISIBLE_DEVICES: "0"
```

**Location**: `./qwex.yaml` or `./qwex.yml` or `./.qwex.yaml`

### `.qwex/config.yaml` (Local Overrides - UNTRACKED)

This file is **not committed to git** and lives in the `.qwex/` directory. Use it for local machine-specific overrides.

```yaml
# .qwex/config.yaml (optional)
artifacts:
  max_file_size_mb: 5000  # override project default

baseUrl: http://localhost:8080  # local dev server
```

**Location**: `./.qwex/config.yaml`

### `.qwex/` Directory Structure

```
.qwex/
  config.yaml        # local overrides (untracked)
  state.yaml         # runtime state (untracked)
  runs/              # run history (untracked)
    abc123/
      run.json
      stdout.log
      files/
```

**Important**: The entire `.qwex/` directory is gitignored (untracked state).

## Configuration Priority

Settings are loaded in this order (later overrides earlier):

1. **Project config**: `qwex.yaml` (tracked)
2. **Local overrides**: `.qwex/config.yaml` (untracked)
3. **Environment variables**: `QWEX_*`
4. **CLI flags**: `--watch`, `--config`, etc.

## Examples

### Setup a new project

```bash
# Create project config
cat > qwex.yaml << EOF
artifacts:
  watch_directories:
    - out
    - models
EOF

# Commit it
git add qwex.yaml
git commit -m "Add qwex config"
```

### Override locally

```bash
# Create local override (not committed)
mkdir -p .qwex
cat > .qwex/config.yaml << EOF
artifacts:
  max_file_size_mb: 10000  # my machine has more space
EOF
```

### Team collaboration

Developer A:
```bash
git clone repo
cd repo
qwex run python train.py  # uses qwex.yaml automatically
```

Developer B:
```bash
git clone repo
cd repo
# Same config, consistent behavior
qwex run python train.py
```

### Cloud submission

```bash
# Qwex reads qwex.yaml and packs it into the JobSpec
qwex run python train.py --cloud
# Cloud agent uses the same artifact rules
```

## Configuration Reference

### Artifacts

```yaml
artifacts:
  watch_directories: [string]     # Dirs to capture artifacts from
  ignore_patterns: [string]       # Glob patterns to ignore
  max_file_size_mb: int          # Max size per file (MB)
  max_total_size_mb: int         # Max total size (MB)
```

**Defaults**:
- `watch_directories`: `["out"]`
- `ignore_patterns`: `["*.tmp", "*.log", "__pycache__", ".git", "node_modules"]`
- `max_file_size_mb`: `1000`
- `max_total_size_mb`: `5000`

### Jobs

Optional named job definitions for convenience:

```yaml
jobs:
  job-name:
    command: string              # Command to run
    args: [string]              # Command arguments
    env: {key: value}           # Environment variables
    working_dir: string         # Working directory
```

Usage: `qwex run job-name` (instead of typing full command)

### API

```yaml
baseUrl: string       # API base URL
apiVersion: string    # API version (default: v1)
```

## See Also

- [Runner Architecture](../LOGBOOK.md#week-8-nov-20-2025)
- [Artifact Capture Design](../LOGBOOK.md#artifact-auto-capture)
