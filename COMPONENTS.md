# Qwex Component System

This document describes the qwex component system and the recent updates.

## Overview

Components are reusable building blocks in qwex. They can be executors, storages, workflows, or any other type of functionality you want to package and reuse.

## Key Changes

### 1. Tags Instead of Kind

Previously, components had a `kind` field with fixed values (`executor`, `storage`, `hook`). Now components use a flexible `tags` field that can contain any number of tags for categorization.

**Before:**
```yaml
name: ssh
kind: executor
```

**After:**
```yaml
name: ssh
tags: [executor, inline]
```

### 2. Steps Structure

Components now support a workflow-style `steps:` structure in addition to the simple `run:` syntax.

**Simple Script (run:):**
```yaml
scripts:
  greet:
    run: |
      echo "Hello, World!"
```

**Multi-Step Workflow (steps:):**
```yaml
scripts:
  deploy:
    steps:
      - name: Build
        run: |
          echo "Building..."
      
      - name: Test
        run: |
          echo "Testing..."
      
      - name: Deploy
        run: |
          echo "Deploying..."
```

**Steps with Component References:**
```yaml
scripts:
  pipeline:
    steps:
      - name: Push code
        uses: storages/git_direct:push
        with:
          REMOTE_URL: "ssh://server/repo.git"
      
      - name: Execute
        uses: executors/ssh:exec
        with:
          HOST: "server"
```

### 3. Function-Based Component References

Component references now include the function name to execute, using the syntax `component:function`.

**Configuration Example:**
```yaml
name: myproject

executor:
  uses: executors/ssh:exec
  vars:
    HOST: myserver
    REPO_ORIGIN: /path/to/repo.git

storage:
  uses: storages/git_direct:push
  vars:
    REMOTE_URL: ssh://user@host/repo.git
```

This makes it explicit which function in the component should be executed.

### 4. Inline by Default

Components are now inline by default, meaning they export specific functions rather than entire classes. For example:

- SSH executor exports only the `exec` function
- Git storage exports only the `push` function

This makes components more modular and easier to compose.

### 5. Variables and Environment

**Compile-time Variables (`vars`):**
Use the `${{ vars.NAME }}` syntax for compile-time variable interpolation:

```yaml
vars:
  MESSAGE: "Hello"

scripts:
  greet:
    run: |
      echo "${{ vars.MESSAGE }}"
```

**Runtime Environment (`env`):**
Standard bash environment variables remain as `$VAR`:

```yaml
scripts:
  show_env:
    run: |
      echo "Path: $PATH"
      echo "Home: $HOME"
      echo "Custom: ${{ vars.CUSTOM }}"
```

## Component Structure

A complete component definition:

```yaml
name: my_component
tags: [executor, custom]
description: My custom component

vars:
  REQUIRED_VAR:
    required: true
    description: A required variable
  
  OPTIONAL_VAR:
    default: "default_value"
    description: An optional variable with default
  
  FLAG_VAR:
    flag: "custom"
    default: "value"
    description: Variable that can be set via CLI flag --custom

scripts:
  # Simple script
  simple:
    description: A simple script
    run: echo "Simple!"
  
  # Multi-step workflow
  complex:
    description: A complex workflow
    steps:
      - name: Step 1
        run: echo "First step"
      
      - name: Step 2
        uses: other/component:function
        with:
          VAR: value
      
      - name: Step 3
        run: echo "Final step"
```

## Step Structure

Each step in a `steps:` list can have:

- `name`: Human-readable step name (optional)
- `uses`: Reference to another component function (e.g., `storages/git:push`)
- `with`: Variables to pass to the component (used with `uses`)
- `run`: Bash command(s) to execute

A step must have either `uses` or `run`, but not both.

## Best Practices

1. **Use tags for categorization**: Add relevant tags like `[executor, remote]` or `[storage, local]`

2. **Prefer steps for complex workflows**: Use `steps:` when you have multiple logical stages

3. **Use function notation in config**: Always specify the function name (e.g., `executors/ssh:exec`)

4. **Separate compile-time and runtime vars**: Use `${{ vars.X }}` for qwex variables, `$X` for bash variables

5. **Document your components**: Add `description` fields to components, vars, and scripts

## Examples

See `examples/workflow_example.yaml` for a complete example demonstrating both `run:` and `steps:` syntax.

## Testing

The component system includes comprehensive tests:

- `tests/test_component.py`: Tests for component loading and structure
- `tests/test_bash_compilation.py`: Tests for bash script compilation
- `tests/test_init.py`: Tests for configuration management

Run tests with:
```bash
cd apps/qwexcli
python3 -m pytest tests/ -v
```
