#!/usr/bin/env bash

QWEX_PREAMBLE="set -euo pipefail
shopt -s expand_aliases

ORIGINAL_PWD=\$(pwd)"

source <(echo "$QWEX_PREAMBLE")

@source() {
  declare -p QWEX_PREAMBLE
  echo "source <(echo \"$QWEX_PREAMBLE\")"
  declare -f task:ssh task:retrieve task:run  @main @help @source @repl
  echo "export SOURCE=\$(@source)"
}

@help() {
  echo "Available tasks:"
  echo "  task:ssh - Connect via SSH and run a command"
  echo "  task:retrieve - Retrieve run artifacts from remote host using scp since rsync is missing"
  echo "  task:run - Execute command in a remote git worktree with environment setup"
  echo ""
  echo "Special commands:"
  echo "  @help        - Show this help message"
  echo "  @source      - Output the full script with all task definitions"
  echo "  @repl [task] - Enter interactive QWEX REPL for a specific task or general commands"
}

# Hash: 0x366566618e13ac60
task:ssh() {
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 testuser@localhost "$@"
}
# Hash: 0xbc905f9d32582c9c
task:retrieve() {
  run_id="$1"
if [ -z "$run_id" ]; then
  echo "Usage: retrieve <RUNID>"
  exit 1
fi

local_run_dir="$HOME/.qwex/runs/$run_id"
mkdir -p "$local_run_dir"

# Use scp instead of rsync because rsync is not available remotely
scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -P 2345 \
  testuser@localhost:.qwex/runs/$run_id/* "$local_run_dir/"
}
# Hash: 0xe3068446f048cfb7
task:run() {
  # Ensure local repo is clean
if [[ -n $(git status --porcelain) ]]; then
  echo "Error: Git repository is not clean. Please commit or stash changes."
  exit 1
fi

run_id="$(date +%Y%m%d%H%M%S)-$(uuidgen | cut -c1-8)"
echo "RUN_ID=$run_id"

# Local storage
local_run_dir="$HOME/.qwex/runs/$run_id"
mkdir -p "$local_run_dir/meta"
cmd_str=""
for arg in "$@"; do
  if [[ "$arg" == *" "* ]]; then
     cmd_str="$cmd_str '$arg'"
  else
     cmd_str="$cmd_str $arg"
  fi
done
echo "${cmd_str:1}" > "$local_run_dir/meta/command"

# Get current commit hash and repo name
current_commit=$(git rev-parse HEAD)
repo_name=$(basename $(git rev-parse --show-toplevel))

remote_repo_dir="\$HOME/.qwex/repos/$repo_name.git"
remote_worktree_dir="$remote_repo_dir/worktree/$run_id"
remote_run_dir="\$HOME/.qwex/runs/$run_id"
remote_log_file="$remote_run_dir/logs/main.log"

# Sync repo to remote
task:ssh "mkdir -p $remote_repo_dir $remote_run_dir/logs"

# Suppress tar warnings about extended headers
COPYFILE_DISABLE=1 tar cf - .git | task:ssh "tar xf - -C $remote_repo_dir"

setup_script="
cd $remote_repo_dir
git --git-dir=.git --work-tree=. worktree add --detach $remote_worktree_dir $current_commit

cd $remote_worktree_dir

# Install uv if needed
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
"

task:ssh "$setup_script"

quoted_args=""
for arg in "$@"; do
  quoted_args="$quoted_args $(printf %q "$arg")"
done

# Source cargo env if it exists, otherwise assume uv is in path or just installed
# Also run uv sync
task:ssh "cd $remote_worktree_dir && [ -f \$HOME/.cargo/env ] && source \$HOME/.cargo/env; uv sync && $quoted_args 2>&1 | tee $remote_log_file"
}

@repl() {
  echo "Entering QWEX REPL. Type 'exit' to quit."
  local task="${1:-}"
  while true; do
    read -rp "qwex ${task:+($task)}> " input
    if [[ "$input" == "exit" ]]; then
      break
    fi
    if [[ -n "$task" ]]; then
      input="task:$task $input"
    fi
    @main $input || true
  done
}

@main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      @help)
        shift
        @help
        return 0
        ;;
      @source)
        shift
        @source
        return 0
        ;;
      @repl)
        shift
        @repl "$@"
        return 0
        ;;
      *) break ;;
    esac
  done

  [[ $# -eq 0 ]] && { @help; return 0; }

  local task="task:$1"
  if declare -f "$task" > /dev/null; then
    shift
    "$task" "$@"
  else
    eval "$@"
  fi
}

export SOURCE=$(@source)

@main "$@"