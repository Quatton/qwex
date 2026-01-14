#!/bin/bash
KEY_PATH="$(dirname "$0")/.ssh/id_rsa"
REPO_NAME="demo" # Assuming repo name is demo based on context
LOCAL_REPO_DIR="$(pwd)" # Assuming ssh.sh is run from inside the repo or we use dirname of script

ssh_cmd() {
    ssh -p 2345 -o StrictHostKeyChecking=no -i "$KEY_PATH" testuser@localhost "$@"
}

run_cmd() {
    # Generate RUN_ID: YYYYMMDDHHMMSS-random
    TIMESTAMP=$(date +%Y%m%d%H%M%S)
    RANDOM_STR=$(LC_ALL=C tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 8)
    RUN_ID="${TIMESTAMP}-${RANDOM_STR}"
    
    echo "RUN_ID=${RUN_ID}"
    
    # Setup local run directory
    RUN_DIR="$HOME/.qwex/runs/$RUN_ID"
    META_DIR="$RUN_DIR/meta"
    mkdir -p "$META_DIR"
    
    # Store the command
    CMD_STR=""
    for arg in "$@"; do
        if [[ "$arg" == *" "* ]]; then
            CMD_STR="$CMD_STR '$arg'"
        else
            CMD_STR="$CMD_STR $arg"
        fi
    done
    REAL_CMD="${CMD_STR:1}"
    echo "$REAL_CMD" > "$META_DIR/command"
    
    # Git sync logic
    # 1. Ensure clean repo
    if [ -n "$(git status --porcelain)" ]; then
        echo "Error: Repository is not clean. Please commit or stash changes."
        exit 1
    fi
    
    # 2. Sync to remote
    REMOTE_REPO_DIR="\$HOME/.qwex/repos/$REPO_NAME.git"
    
    # Ensure remote bare repo exists (or empty dir to push to)
    # Ideally we want a bare repo to push to, or just a directory to sync to.
    # Requirement says: "synchronize any changes from local to remote's $HOME/.qwex/repos/<reponame>.git"
    # And "Inside that git repo, we create a worktree" implies it's a git repo.
    
    # Let's initialize remote repo if it doesn't exist
    ssh_cmd "mkdir -p $REMOTE_REPO_DIR && cd $REMOTE_REPO_DIR && if [ ! -d HEAD ]; then git init --bare; fi"
    
    # Push changes to remote
    # We can add the remote and push
    git remote add qwex-remote "ssh://testuser@localhost:2345/home/testuser/.qwex/repos/$REPO_NAME.git" 2>/dev/null
    # Fix remote URL if it already exists but is different/broken (or just ignore error)
    git remote set-url qwex-remote "ssh://testuser@localhost:2345/home/testuser/.qwex/repos/$REPO_NAME.git"
    
    GIT_SSH_COMMAND="ssh -p 2345 -o StrictHostKeyChecking=no -i $KEY_PATH" git push qwex-remote HEAD:refs/heads/main -f
    
    CURRENT_HASH=$(git rev-parse HEAD)
    
    # 3. Create worktree on remote
    REMOTE_WORKTREE_DIR="\$HOME/.qwex/repos/$REPO_NAME.git/worktree/$RUN_ID"
    
    # 4. Custom init command (uv check/install and sync)
    # 5. Run command inside worktree
    
    REMOTE_LOG_DIR="\$HOME/.qwex/runs/$RUN_ID/logs"
    REMOTE_LOG_FILE="$REMOTE_LOG_DIR/main.log"
    
    REMOTE_SCRIPT="
    set -e
    mkdir -p $REMOTE_LOG_DIR
    
    # Create worktree
    cd $REMOTE_REPO_DIR
    git worktree add -f $REMOTE_WORKTREE_DIR $CURRENT_HASH
    
    cd $REMOTE_WORKTREE_DIR
    
    # Init uv
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source \$HOME/.cargo/env
    fi
    uv sync
    
    # Run command and log
    $REAL_CMD > $REMOTE_LOG_FILE 2>&1
    "
    
    # Execute remote script
    # We need to preserve the script content through ssh
    ssh_cmd "$REMOTE_SCRIPT"
    
    # Output logs
    ssh_cmd "cat $REMOTE_LOG_FILE"
}

retrieve_cmd() {
    RUN_ID="$1"
    if [ -z "$RUN_ID" ]; then
        echo "Usage: $0 retrieve <RUNID>"
        exit 1
    fi

    LOCAL_RUN_DIR="$HOME/.qwex/runs/$RUN_ID"
    mkdir -p "$LOCAL_RUN_DIR"
    
    rsync -avz -e "ssh -p 2345 -o StrictHostKeyChecking=no -i $KEY_PATH" \
        testuser@localhost:.qwex/runs/"$RUN_ID"/ "$LOCAL_RUN_DIR"/
}

COMMAND="$1"
if [ -n "$COMMAND" ]; then
    shift
fi

case "$COMMAND" in
    ssh)
        ssh_cmd "$@"
        ;;
    run)
        run_cmd "$@"
        ;;
    retrieve)
        retrieve_cmd "$@"
        ;;
    *)
        echo "Usage: $0 {ssh|run|retrieve} [command]"
        exit 1
        ;;
esac
