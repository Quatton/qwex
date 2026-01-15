#!/usr/bin/env bash

QWEX_PREAMBLE="set -uo pipefail
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
  echo "  task:ssh - Connects to the remote SSH server and runs the provided arguments as a command."
  echo "  task:run - Syncs git repo, creates remote worktree, and executes command."
  echo "  task:retrieve - Retrieves the run directory from remote to local."
  echo ""
  echo "Special commands:"
  echo "  @help        - Show this help message"
  echo "  @source      - Output the full script with all task definitions"
  echo "  @repl [task] - Enter interactive QWEX REPL for a specific task or general commands"
}

# Hash: 0x3516fe8ea57fbffe
task:ssh() {
  ssh -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$@"
}
# Hash: 0x8f45efd5b321612d
task:run() {
  # 1. Check Local Git Status
if [ -n "$(git status --porcelain)" ]; then
  echo "Error: Git working tree is not clean. Please commit or stash changes."
  exit 1
fi

RUN_ID=$(date +%Y%m%d%H%M%S)-$(openssl rand -hex 4)
CMD="$@"
COMMIT_HASH=$(git rev-parse HEAD)

# 2. Sync Repo
# Ensure remote bare repo exists
REPO_DIR=".qwex/repos/demo.git"
# We check if HEAD exists to avoid re-initing unnecessarily, though init is safe.
ssh -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "mkdir -p $REPO_DIR && [ ! -d $REPO_DIR/HEAD ] && git init --bare $REPO_DIR || true"


# Push to remote
REMOTE_REPO_PATH="/home/testuser/$REPO_DIR"
GIT_SSH_COMMAND="ssh -i /Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
git push "ssh://testuser@localhost/$REMOTE_REPO_PATH" HEAD:refs/heads/qwex-sync -f > /dev/null 2>&1

if [ $? -ne 0 ]; then
  echo "Error: Failed to sync git repository to remote."
  exit 1
fi

# 3. Setup Remote Environment (Logs & Worktree)
REMOTE_RUN_DIR="\$HOME/.qwex/runs/$RUN_ID"
WORKTREE_DIR="$REMOTE_RUN_DIR/worktree"

# Create log/meta structure
SETUP_CMD="mkdir -p $REMOTE_RUN_DIR/logs $REMOTE_RUN_DIR/meta && echo \"$CMD\" > $REMOTE_RUN_DIR/meta/command"
ssh -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$SETUP_CMD"


# Create worktree from the bare repo
# We use the full path for the bare repo in the worktree command
# git --git-dir=... worktree add ...
WORKTREE_CMD="git --git-dir=\$HOME/$REPO_DIR worktree add -d $WORKTREE_DIR $COMMIT_HASH"
ssh -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$WORKTREE_CMD"


# 4. Execute in Worktree
# We enter the worktree, run the command, and pipe output to the log file
# We assume the command (e.g. 'uv run main.py') works relative to the repo root
EXEC_CMD="cd $WORKTREE_DIR && { $CMD; } 2>&1 | tee $REMOTE_RUN_DIR/logs/main.log"
ssh -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -p 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost "$EXEC_CMD"


echo "RUN_ID=$RUN_ID"
}
# Hash: 0x6b22d546252e33a5
task:retrieve() {
  if [ -z "" ]; then
  if [ $# -eq 0 ]; then
    echo "Error: Run ID is required."
    exit 1
  fi
  RUN_ID="$1"
else
  RUN_ID=""
fi

LOCAL_RUN_DIR="$HOME/.qwex/runs/$RUN_ID"
mkdir -p "$LOCAL_RUN_DIR"

# Use scp to recursively copy the remote directory content to local
# We exclude the worktree itself if it's large? The instructions don't say to exclude it.
# But 'worktree' is a directory inside the run dir now.
# We probably only care about logs and meta for verification.
# But scp -r copies everything.

scp -r -i "/Users/quatton/Documents/GitHub/qwex/playground/opencode-eval/demo/.ssh/id_rsa" -P 2345 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null testuser@localhost:.qwex/runs/$RUN_ID/* "$LOCAL_RUN_DIR/"
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