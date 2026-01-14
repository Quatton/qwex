#!/usr/bin/env bash

QWEX_PREAMBLE="set -euo pipefail
shopt -s expand_aliases

ORIGINAL_PWD=\$(pwd)"

source <(echo "$QWEX_PREAMBLE")

@source() {
  declare -p QWEX_PREAMBLE
  echo "source <(echo \"$QWEX_PREAMBLE\")"
  declare -f task:ssh task:run task:retrieve  @main @help @source @repl
  echo "export SOURCE=\$(@source)"
}

@help() {
  echo "Available tasks:"
  echo "  task:ssh - Run a command on the remote server via SSH"
  echo "  task:run - Run command via SSH with Run ID, logging, and Git Worktree"
  echo "  task:retrieve - Retrieve run directory from remote host"
  echo ""
  echo "Special commands:"
  echo "  @help        - Show this help message"
  echo "  @source      - Output the full script with all task definitions"
  echo "  @repl [task] - Enter interactive QWEX REPL for a specific task or general commands"
}

# Hash: 0x6c5db72cec46c592
task:ssh() {
  ssh -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$@"
}
# Hash: 0x42853a465855031c
task:run() {
  # Check for clean git repo
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: Git repository is not clean. Please commit or stash changes." >&2
  exit 1
fi

RUN_ID="$(date +%Y%m%d%H%M%S)-$(openssl rand -hex 4)"
REPO_NAME=$(basename $(git rev-parse --show-toplevel))
COMMIT_HASH=$(git rev-parse HEAD)

QWEX_RUN_DIR="$HOME/.qwex/runs/$RUN_ID"
mkdir -p "$QWEX_RUN_DIR/meta"

cmd_str=""
for arg in "$@"; do
  if [[ "$arg" == *" "* ]]; then
    cmd_str="$cmd_str '$arg'"
  else
    cmd_str="$cmd_str $arg"
  fi
done
echo "${cmd_str:1}" > "$QWEX_RUN_DIR/meta/command"

REMOTE_REPO_DIR="\$HOME/.qwex/repos/$REPO_NAME.git"
REMOTE_WORKTREE_DIR="\$HOME/.qwex/repos/$REPO_NAME.git/worktree/$RUN_ID"
REMOTE_RUN_DIR="\$HOME/.qwex/runs/$RUN_ID"

REMOTE_SCRIPT="
set -e
mkdir -p $REMOTE_WORKTREE_DIR
"
ssh -q -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$REMOTE_SCRIPT" >/dev/null 2>&1

tar cf - . | ssh -q -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "tar xf - -C $REMOTE_WORKTREE_DIR" >/dev/null 2>&1

# Execute command
REMOTE_EXEC_SCRIPT="
set -e
cd $REMOTE_WORKTREE_DIR

# Install uv if needed
if ! command -v uv &> /dev/null; then
  if [ ! -f \"\$HOME/.local/bin/uv\" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  fi
  export PATH=\"\$HOME/.local/bin:\$PATH\"
fi

uv sync >/dev/null 2>&1

mkdir -p \"$REMOTE_RUN_DIR/logs\"
{ ${cmd_str:1} 2>&1 | tee \"$REMOTE_RUN_DIR/logs/main.log\"; }
"

# Execute remote script (use -q for ssh)
ssh -q -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$REMOTE_EXEC_SCRIPT"

echo "RUN_ID=$RUN_ID"
}
# Hash: 0x955690cb9b1b39c6
task:retrieve() {
  RUN_ID="$1"
if [ -z "$RUN_ID" ]; then
  echo "Usage: ./ssh.sh retrieve <RUNID>"
  exit 1
fi

LOCAL_RUN_DIR="$HOME/.qwex/runs/$RUN_ID"
mkdir -p "$LOCAL_RUN_DIR"

scp -q -r -P 2345 -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost:.qwex/runs/$RUN_ID/* "$LOCAL_RUN_DIR/"
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