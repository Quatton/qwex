# QWEX Workflow Language (qwl)

A YAML-based workflow language that compiles to standalone bash scripts.

## Installation

```bash
bun install
```

## Usage

### Basic Structure

A qwl file is a YAML file with three main sections:

```yaml
modules:
  # Import and organize other qwl files
  utils:
    uses: ./utils.yaml

vars:
  # Define variables
  greeting: Hello

tasks:
  # Define executable tasks
  sayHello:
    cmd: 'echo "{{ vars.greeting }}"'
```

### Variables

Variables are defined in the `vars` section and referenced using `{{ vars.name }}`:

```yaml
vars:
  message: Hello, World!
  name: Alice
  greeting: "{{ vars.message }} I'm {{ vars.name }}"

tasks:
  greet:
    cmd: 'echo "{{ vars.greeting }}"'
```

**Variable Precedence**: Task-level variables override module-level variables:

```yaml
vars:
  message: module-level

tasks:
  useModuleVar:
    cmd: 'echo "{{ vars.message }}"'  # outputs: module-level
  
  useTaskVar:
    vars:
      message: task-level
    cmd: 'echo "{{ vars.message }}"'  # outputs: task-level
```

### Tasks

Tasks are executable units that compile to bash functions:

```yaml
tasks:
  build:
    desc: "Build the project"
    cmd: npm run build
  
  test:
    desc: "Run tests"
    cmd: npm test
```

**Task References**: Call other tasks using `{{ tasks.taskName }}`:

```yaml
tasks:
  setup:
    cmd: echo "Setting up..."
  
  build:
    cmd: |
      {{ tasks.setup }}
      npm run build
```

This creates a dependency - `setup()` function is called from `build()`.

**Task Inlining**: Use `.inline()` to paste task code directly instead of creating a function call:

```yaml
tasks:
  helper:
    cmd: echo "Helper code"
  
  main:
    cmd: |
      # Code is inlined, no function call
      {{ tasks.helper.inline() }}
      echo "More code"
```

**Shorthand Syntax**: Reference tasks without the `tasks.` prefix:

```yaml
tasks:
  setup:
    cmd: echo "Setup"
  
  build:
    cmd: |
      {{ setup }}  # same as {{ tasks.setup }}
```

### Modules

Modules allow you to organize and reuse qwl files:

**External Modules** - import another file:

```yaml
modules:
  logger:
    uses: ./logger.yaml
  
tasks:
  main:
    cmd: |
      {{ modules.logger.tasks.info }} hello
```

**Inline Modules** - define modules directly:

```yaml
modules:
  utils:
    vars:
      prefix: "[UTIL]"
    tasks:
      log:
        cmd: 'echo "{{ vars.prefix }} $1"'

tasks:
  main:
    cmd: |
      {{ modules.utils.tasks.log }}
```

**Module Variables**: Modules can override variables for their scope:

```yaml
uses: ./base.yaml  # inherits from base.yaml

modules:
  custom:
    uses: ./base.yaml
    vars:
      origin: custom-value  # overrides vars in base.yaml
```

**Module Shortcuts**: Reference module tasks without the `modules.` prefix:

```yaml
modules:
  logger:
    uses: ./logger.yaml

tasks:
  main:
    cmd: |
      {{ logger.tasks.info }}  # same as {{ modules.logger.tasks.info }}
      {{ logger.info }} # even shorter
```

### Special Functions

**`uses()` Function** - include external files or inline tasks:

Include a shell script file:
```yaml
tasks:
  deploy:
    cmd: |
      {{ uses("./deploy-script.sh") }}
```

### Special Tags

**Heredoc Tag** - `{% eof %}` creates bash heredoc with unique delimiters:

```yaml
tasks:
  writeConfig:
    cmd: |
      cat << {% eof %}
      {
        "name": "{{ vars.appName }}",
        "version": "1.0.0"
      }
      {% endeof %} > config.json
```

Compiles to:
```bash
writeConfig() {
cat << 'EOF_A1B2C3D4'
{
  "name": "MyApp",
  "version": "1.0.0"
}
EOF_A1B2C3D4 > config.json
}
```

**Context Tag** - `{% context %}` exports function definitions for container contexts:

```yaml
tasks:
  helper:
    cmd: echo "Helper"
  
  runInDocker:
    cmd: |
      docker run --rm alpine sh -c '
      {% context %}
      {{ tasks.helper }}
      {% endcontext %}
      helper
      '
```

Compiles to:
```bash
docker run --rm alpine sh -c '
$(declare -f helper)
helper
'
```

### Output

qwl compiles to a standalone bash script with:
- All tasks as bash functions
- `@help` command listing available tasks
- `@main` dispatcher that routes to the correct task
- Proper error handling with `set -euo pipefail`

Example output structure:
```bash
#!/usr/bin/env bash
set -euo pipefail

@help() {
  echo "Available tasks:"
  echo "  build"
  echo "  test"
}

build() {
  npm run build
}

test() {
  npm test
}

@main() {
  case "${1:-}" in
    "build") shift; build "$@" ;;
    "test") shift; test "$@" ;;
    *) @help; exit 1 ;;
  esac
}

@main "$@"
```

### Complete Example

```yaml
# logger.yaml
vars:
  prefix: "[LOG]"

tasks:
  info:
    cmd: 'echo "{{ vars.prefix }} INFO: $1"'
  error:
    cmd: 'echo "{{ vars.prefix }} ERROR: $1" >&2'
```

```yaml
# main.yaml
uses: ./logger.yaml  # inherit from logger.yaml

vars:
  projectName: MyApp

modules:
  builder:
    vars:
      buildDir: ./dist
    tasks:
      clean:
        cmd: 'rm -rf {{ vars.buildDir }}'
      compile:
        cmd: 'tsc --outDir {{ vars.buildDir }}'

tasks:
  build:
    desc: "Build the project"
    cmd: |
      {{ tasks.info }} "Building {{ vars.projectName }}..."
      {{ modules.builder.tasks.clean }}
      {{ modules.builder.tasks.compile }}
      {{ tasks.info }} "Build complete!"
  
  deploy:
    desc: "Deploy the project"
    vars:
      deployScript: ./deploy.sh
    cmd: |
      {{ tasks.build }}
      {{ uses(vars.deployScript) }}
```