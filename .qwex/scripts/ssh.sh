#!/usr/bin/env bash
# ssh.sh - qwex SSH runner CLI
# Usage:
#   ./ssh.sh run <command>       - Run command on remote
#   ./ssh.sh run < script.sh     - Run script from stdin on remote
#   ./ssh.sh log [run-id]        - Show logs for a run
#   ./ssh.sh cancel [run-id]     - Cancel a running job
#   ./ssh.sh pull [run-id]       - Pull run logs from remote
#   ./ssh.sh list                - List all runs

set -euo pipefail

# --- Configuration (override via env) ---
PUSH_ON_RUN=${PUSH_ON_RUN:-"true"}
FAIL_ON_DIRTY=${FAIL_ON_DIRTY:-"true"}
QWEX_SSH_TARGET=${QWEX_SSH_TARGET:-"qtn@csc"}
QWEX_SSH_PORT=${QWEX_SSH_PORT:-22}

# Local paths
LOCAL_RUN_DIR=${LOCAL_RUN_DIR:-"$(pwd)/.qwex/_internal/runs"}

# Remote paths (these get expanded on remote side)
REMOTE_REPO_CACHE=${REMOTE_REPO_CACHE:-'$HOME/repos/qwex-cache'}
REMOTE_RUN_DIR=${REMOTE_RUN_DIR:-'$HOME/.qwex/runs'}
# This is where the remote fetches from (local path to the bare repo we push to)
REMOTE_REPO_ORIGIN=${REMOTE_REPO_ORIGIN:-'/home/qtn/repos/qwex.git'}

# Git remote config (this is the URL we push to from local)
GIT_REMOTE_URL=${GIT_REMOTE_URL:-"ssh://$QWEX_SSH_TARGET/home/qtn/repos/qwex.git"}
GIT_REMOTE_NAME=${GIT_REMOTE_NAME:-"direct"}

# --- Utilities ---
now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
sanitize_ns() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g'; }

log_info() { echo "[qwex:ssh] $*"; }
log_error() { echo "[qwex:ssh] ERROR: $*" >&2; }
die() { log_error "$*"; exit 1; }

ssh_cmd() {
  ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "$@"
}

generate_run_id() {
  local namespace
  namespace=$(sanitize_ns "${QWEX_NAMESPACE:-$(basename "$(pwd)")}")
  local ts rand
  ts=$(date +%Y%m%dT%H%M%S)
  rand=$(printf '%04x%04x' $RANDOM $RANDOM)
  echo "${namespace}-${ts}-${rand}"
}

# --- Git helpers ---
ensure_git_repo() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not inside a git repository"
}

check_clean_worktree() {
  if [ "$FAIL_ON_DIRTY" = "true" ]; then
    if ! git diff --quiet || ! git diff --cached --quiet; then
      die "repository has uncommitted changes; commit or stash first"
    fi
  fi
}

ensure_remote() {
  local current_url
  current_url=$(git remote get-url "$GIT_REMOTE_NAME" 2>/dev/null || true)
  if [ -z "$current_url" ]; then
    log_info "adding remote '$GIT_REMOTE_NAME' -> $GIT_REMOTE_URL"
    git remote add "$GIT_REMOTE_NAME" "$GIT_REMOTE_URL"
  elif [ "$current_url" != "$GIT_REMOTE_URL" ]; then
    die "remote '$GIT_REMOTE_NAME' URL mismatch. Run: git remote set-url $GIT_REMOTE_NAME $GIT_REMOTE_URL"
  fi
}

push_if_needed() {
  if [ "$PUSH_ON_RUN" = "true" ]; then
    log_info "pushing to $GIT_REMOTE_NAME..."
    git push "$GIT_REMOTE_NAME" --set-upstream HEAD -q || die "git push failed"
  else
    local local_sha remote_sha
    local_sha=$(git rev-parse HEAD)
    remote_sha=$(git ls-remote "$GIT_REMOTE_URL" HEAD 2>/dev/null | awk '{print $1}')
    [ "$local_sha" = "$remote_sha" ] || die "local HEAD doesn't match remote (PUSH_ON_RUN=false)"
  fi
}

# --- Command: run ---
cmd_run() {
  ensure_git_repo
  check_clean_worktree
  ensure_remote
  push_if_needed

  local git_head run_id
  git_head=$(git rev-parse HEAD)
  run_id=$(generate_run_id)

  log_info "run id: $run_id"
  log_info "commit: $git_head"

  # Build the command to run
  local user_cmd user_cmd_b64 tmp_script=""
  if [ "$#" -gt 0 ]; then
    user_cmd="$*"
    user_cmd_b64=$(printf '%s' "$user_cmd" | base64)
  else
    # Read from stdin into a temp file
    tmp_script=$(mktemp)
    cat > "$tmp_script"
    user_cmd="STDIN_SCRIPT"
    user_cmd_b64=$(printf '%s' "$user_cmd" | base64)
  fi

  # Build remote script that:
  # 1. Init phase: ensure repo cache, fetch if needed
  # 2. Run-wrapping: create worktree, setup meta dirs, trap cleanup
  # 3. Run phase: execute command, log output
  local remote_script
  remote_script=$(cat <<'REMOTE_SCRIPT_TEMPLATE'
#!/usr/bin/env bash
set -euo pipefail

# --- Config passed from local ---
GIT_HEAD="__GIT_HEAD__"
RUN_ID="__RUN_ID__"
REMOTE_REPO_CACHE="__REMOTE_REPO_CACHE__"
REMOTE_RUN_DIR="__REMOTE_RUN_DIR__"
REMOTE_REPO_ORIGIN="__REMOTE_REPO_ORIGIN__"
USER_CMD_B64="__USER_CMD_B64__"

# Decode user command from base64
USER_CMD=$(echo "$USER_CMD_B64" | base64 -d)

# Expand $HOME in paths
REMOTE_REPO_CACHE=$(eval echo "$REMOTE_REPO_CACHE")
REMOTE_RUN_DIR=$(eval echo "$REMOTE_RUN_DIR")

# Paths
WORKTREE_DIR="/tmp/qwex-run-$RUN_ID"
META_DIR="$REMOTE_RUN_DIR/$RUN_ID/meta"
LOG_DIR="$REMOTE_RUN_DIR/$RUN_ID/logs"

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# Cleanup function for remote
cleanup_remote() {
  local rc=$?
  echo "[remote] cleaning up worktree..."
  if [ -d "$WORKTREE_DIR" ]; then
    git -C "$REMOTE_REPO_CACHE" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
  fi
  exit $rc
}

# --- Init phase ---
echo "[remote] init phase: ensuring repo cache at $REMOTE_REPO_CACHE"

if [ ! -d "$REMOTE_REPO_CACHE" ]; then
  echo "[remote] cloning repo cache from $REMOTE_REPO_ORIGIN..."
  mkdir -p "$(dirname "$REMOTE_REPO_CACHE")"
  git clone "$REMOTE_REPO_ORIGIN" "$REMOTE_REPO_CACHE"
elif [ -d "$REMOTE_REPO_CACHE/.git" ]; then
  # Non-bare repo - fetch from origin if configured
  echo "[remote] fetching updates (non-bare)..."
  git -C "$REMOTE_REPO_CACHE" fetch origin --prune 2>/dev/null || true
else
  # Bare repo - fetch from origin
  echo "[remote] fetching updates (bare)..."
  git -C "$REMOTE_REPO_CACHE" fetch origin --prune 2>/dev/null || true
fi

# --- Run-wrapping phase ---
echo "[remote] creating worktree for $GIT_HEAD"
mkdir -p "$META_DIR" "$LOG_DIR"

# Check if commit exists
if ! git -C "$REMOTE_REPO_CACHE" cat-file -e "$GIT_HEAD^{commit}" 2>/dev/null; then
  echo "[remote] ERROR: commit $GIT_HEAD not found in cache" >&2
  exit 1
fi

git -C "$REMOTE_REPO_CACHE" worktree add --detach "$WORKTREE_DIR" "$GIT_HEAD"
trap cleanup_remote EXIT

cd "$WORKTREE_DIR"
echo "[remote] worktree ready at $WORKTREE_DIR"

# Write initial metadata
echo "$GIT_HEAD" > "$META_DIR/commit"
now_iso > "$META_DIR/created_at"
echo "$$" > "$META_DIR/pid"

# --- Run phase ---
echo "[remote] starting command..."
now_iso > "$META_DIR/started_at"
echo "running" > "$META_DIR/status"

set +e
if [ "$USER_CMD" = "STDIN_SCRIPT" ]; then
  # Copy stdin script from temp location to worktree
  cp "${STDIN_SCRIPT_PATH:-/dev/null}" ./run.sh
  chmod +x ./run.sh
  ./run.sh > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
else
  bash -c "$USER_CMD" > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
fi
exit_code=$?
set -e

now_iso > "$META_DIR/finished_at"
echo "$exit_code" > "$META_DIR/exit_code"
if [ "$exit_code" -eq 0 ]; then
  echo "succeeded" > "$META_DIR/status"
else
  echo "failed" > "$META_DIR/status"
fi

echo "[remote] finished with exit code $exit_code"
exit $exit_code
REMOTE_SCRIPT_TEMPLATE
)

  # Substitute variables
  remote_script=${remote_script//__GIT_HEAD__/$git_head}
  remote_script=${remote_script//__RUN_ID__/$run_id}
  remote_script=${remote_script//__REMOTE_REPO_CACHE__/$REMOTE_REPO_CACHE}
  remote_script=${remote_script//__REMOTE_RUN_DIR__/$REMOTE_RUN_DIR}
  remote_script=${remote_script//__REMOTE_REPO_ORIGIN__/$REMOTE_REPO_ORIGIN}
  remote_script=${remote_script//__USER_CMD_B64__/$user_cmd_b64}

  # Handle Ctrl+C gracefully
  local ssh_pid
  trap 'handle_interrupt' INT

  handle_interrupt() {
    echo ""
    read -r -p "[qwex:ssh] Interrupt received. Cancel remote job? [y/N] " response
    case "$response" in
      [yY]|[yY][eE][sS])
        log_info "cancelling job $run_id..."
        cmd_cancel "$run_id"
        exit 130
        ;;
      *)
        log_info "continuing... (press Ctrl+C again to force quit)"
        ;;
    esac
  }

  log_info "executing on remote..."
  
  if [ "$user_cmd" = "STDIN_SCRIPT" ]; then
    # First send the remote wrapper script
    echo "$remote_script" | ssh_cmd "cat > /tmp/qwex-wrapper-$run_id.sh && chmod +x /tmp/qwex-wrapper-$run_id.sh"
    
    # Upload the stdin script to a known location
    cat "$tmp_script" | ssh_cmd "cat > /tmp/qwex-stdin-$run_id.sh"
    rm -f "$tmp_script"
    
    # Run the wrapper (it will copy the stdin script to the worktree)
    ssh_cmd "STDIN_SCRIPT_PATH=/tmp/qwex-stdin-$run_id.sh bash /tmp/qwex-wrapper-$run_id.sh; rm -f /tmp/qwex-wrapper-$run_id.sh /tmp/qwex-stdin-$run_id.sh"
    exit_code=$?
  else
    echo "$remote_script" | ssh_cmd "bash -s"
    exit_code=$?
  fi

  trap - INT
  
  log_info "run complete: $run_id (exit=$exit_code)"
  return $exit_code
}

# --- Command: log ---
cmd_log() {
  local run_id="${1:-}"
  
  if [ -z "$run_id" ]; then
    # Show latest run
    run_id=$(cmd_list_latest)
    [ -n "$run_id" ] || die "no runs found"
  fi
  
  log_info "fetching logs for $run_id..."
  
  ssh_cmd "cat \$HOME/.qwex/runs/$run_id/logs/stdout.log 2>/dev/null" || true
  ssh_cmd "cat \$HOME/.qwex/runs/$run_id/logs/stderr.log 2>/dev/null" >&2 || true
}

# --- Command: cancel ---
cmd_cancel() {
  local run_id="${1:-}"
  
  if [ -z "$run_id" ]; then
    run_id=$(cmd_list_latest)
    [ -n "$run_id" ] || die "no runs found"
  fi
  
  log_info "cancelling $run_id..."
  
  # Get PID and kill it
  local pid
  pid=$(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/pid 2>/dev/null" || true)
  
  if [ -n "$pid" ]; then
    ssh_cmd "kill -TERM $pid 2>/dev/null || kill -KILL $pid 2>/dev/null" || true
    ssh_cmd "echo 'cancelled' > \$HOME/.qwex/runs/$run_id/meta/status"
    log_info "sent kill signal to pid $pid"
  else
    log_info "no pid found for $run_id"
  fi
}

# --- Command: pull ---
cmd_pull() {
  local run_id="${1:-}"
  
  mkdir -p "$LOCAL_RUN_DIR"
  
  if [ -z "$run_id" ]; then
    log_info "pulling all runs to $LOCAL_RUN_DIR..."
    rsync -avz --progress -e "ssh -p $QWEX_SSH_PORT" \
      "$QWEX_SSH_TARGET:\$HOME/.qwex/runs/" "$LOCAL_RUN_DIR/"
  else
    log_info "pulling $run_id to $LOCAL_RUN_DIR..."
    rsync -avz --progress -e "ssh -p $QWEX_SSH_PORT" \
      "$QWEX_SSH_TARGET:\$HOME/.qwex/runs/$run_id/" "$LOCAL_RUN_DIR/$run_id/"
  fi
  
  log_info "done"
}

# --- Command: list ---
cmd_list() {
  ssh_cmd "ls -1t \$HOME/.qwex/runs/ 2>/dev/null" || echo "(no runs)"
}

cmd_list_latest() {
  ssh_cmd "ls -1t \$HOME/.qwex/runs/ 2>/dev/null | head -1"
}

# --- Command: status ---
cmd_status() {
  local run_id="${1:-}"
  
  if [ -z "$run_id" ]; then
    run_id=$(cmd_list_latest)
    [ -n "$run_id" ] || die "no runs found"
  fi
  
  echo "Run: $run_id"
  echo "Status: $(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/status 2>/dev/null" || echo "unknown")"
  echo "Commit: $(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/commit 2>/dev/null" || echo "unknown")"
  echo "Started: $(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/started_at 2>/dev/null" || echo "unknown")"
  echo "Finished: $(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/finished_at 2>/dev/null" || echo "unknown")"
  echo "Exit: $(ssh_cmd "cat \$HOME/.qwex/runs/$run_id/meta/exit_code 2>/dev/null" || echo "unknown")"
}

# --- Main ---
usage() {
  cat <<EOF
qwex SSH runner

Usage:
  $0 run <command...>     Run command on remote
  $0 run < script.sh      Run script from stdin
  $0 log [run-id]         Show logs (default: latest)
  $0 cancel [run-id]      Cancel a run
  $0 pull [run-id]        Pull logs locally
  $0 list                 List all runs
  $0 status [run-id]      Show run status

Environment:
  QWEX_SSH_TARGET         SSH target (default: qtn@csc)
  QWEX_SSH_PORT           SSH port (default: 22)
  PUSH_ON_RUN             Push before run (default: true)
  FAIL_ON_DIRTY           Fail on dirty worktree (default: true)
  REMOTE_REPO_CACHE       Remote working repo cache
  REMOTE_REPO_ORIGIN      Remote path to fetch from (the bare repo we push to)
  REMOTE_RUN_DIR          Remote run data path
EOF
}

main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    run)
      cmd_run "$@"
      ;;
    log|logs)
      cmd_log "$@"
      ;;
    cancel)
      cmd_cancel "$@"
      ;;
    pull)
      cmd_pull "$@"
      ;;
    list|ls)
      cmd_list "$@"
      ;;
    status)
      cmd_status "$@"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      log_error "unknown command: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
