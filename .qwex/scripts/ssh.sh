#!/usr/bin/env bash
# ssh.sh - qwex SSH runner
# Behavior:
# - enforce clean git working tree
# - ensure origin remote is set to https://github.com/Quatton/qwex.git (configurable)
# - optionally push on run (PUSH_ON_RUN=true/false)
# - create a temporary git worktree in /tmp, rsync it to remote, execute command there via ssh
# - record metadata under ~/.qwex/runs/<run-id>/meta: created_at, started_at, finished_at, status, exit_code, commit (as github/<sha>)
# - stream raw stdout/stderr and tee to logs
# - remove scratch (worktree and remote dir) on completion

set -euo pipefail

# --- configuration (can be overridden by env) ---
PUSH_ON_RUN=${PUSH_ON_RUN:-"true"}   # "true" or "false"
QWEX_RUNS_DIR=${QWEX_RUNS_DIR:-"$HOME/.qwex/runs"}
QWEX_SSH_TARGET=${QWEX_SSH_TARGET:-"qtn@csc"} # required: user@host
QWEX_SSH_PORT=${QWEX_SSH_PORT:-22}

if [ -z "$QWEX_SSH_TARGET" ]; then
  echo "QWEX_SSH_TARGET not set (e.g. user@host). Aborting." >&2
  exit 2
fi

GIT_REMOTE_URL=${GIT_REMOTE_URL:-"ssh://$QWEX_SSH_TARGET/home/qtn/repos/qwex.git"}
GIT_REMOTE_NAME=${GIT_REMOTE_NAME:-"direct"}

REPO_BASENAME_RAW=${GIT_REMOTE_URL##*/}
REPO_BASENAME=${REPO_BASENAME_RAW%.git}
REMOTE_CACHE_DIR=${REMOTE_CACHE_DIR:-'$HOME/.qwex/cache/'$REPO_BASENAME}

# For logging locally, show the literal remote cache path (without expanding $HOME locally)
REMOTE_CACHE_DISPLAY=${REMOTE_CACHE_DISPLAY:-"$REMOTE_CACHE_DIR"}

now_iso(){ date --iso-8601=seconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ"; }
ensure_dir(){ mkdir -p "$@"; }
sanitize_ns(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g'; }


for cmd in git ssh; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "required command not found: $cmd" >&2
    exit 2
  fi
done

# --- run id ---
NAMESPACE=${QWEX_NAMESPACE:-$(basename "$(pwd)")}
NAMESPACE=$(sanitize_ns "$NAMESPACE")
TS=$(date +%Y%m%dT%H%M%S%N)
RAND=$(printf '%04x%04x' $RANDOM $RANDOM)
RUN_ID="${NAMESPACE}-${TS}-${RAND}"

RUN_DIR="$QWEX_RUNS_DIR/$RUN_ID"
META_DIR="$RUN_DIR/meta"
LOG_DIR="$RUN_DIR/logs"
ensure_dir "$META_DIR" "$LOG_DIR"

printf '%s' "$(now_iso)" > "$META_DIR/created_at"

# --- git checks ---
echo "[qwex:ssh] verifying git repository..."
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not inside a git repository" >&2
  exit 2
fi

GIT_HEAD=$(git rev-parse HEAD)

# fail on dirty
if [ -n "$(git status --porcelain)" ]; then
  echo "repository has uncommitted changes; aborting" >&2
  exit 2
fi

# ensure configured remote name matches desired remote URL
REMOTE_URL=$(git remote get-url "$GIT_REMOTE_NAME" 2>/dev/null || true)
if [ -z "$REMOTE_URL" ]; then
  git remote add "$GIT_REMOTE_NAME" "$GIT_REMOTE_URL"
  REMOTE_URL=$GIT_REMOTE_URL
fi
if [ "$REMOTE_URL" != "$GIT_REMOTE_URL" ]; then
  echo "remote '$GIT_REMOTE_NAME' URL ($REMOTE_URL) does not match desired URL ($GIT_REMOTE_URL); aborting" >&2
  echo "To fix, run: git remote set-url $GIT_REMOTE_NAME $GIT_REMOTE_URL" >&2
  exit 2
fi

if [ "$PUSH_ON_RUN" = "true" ]; then
  echo "[qwex:ssh] pushing current branch to $GIT_REMOTE_NAME..."
  if ! git push "$GIT_REMOTE_NAME" --set-upstream --quiet HEAD; then
    echo "git push failed; ensure credentials are available" >&2
    exit 2
  fi
else
  # verify remote SHA matches
  REMOTE_SHA=$(git ls-remote "$GIT_REMOTE_URL" HEAD 2>/dev/null | awk '{print $1}')
  if [ -z "$REMOTE_SHA" ]; then
    echo "could not determine remote HEAD for $GIT_REMOTE_URL" >&2
    exit 2
  fi
  if [ "$REMOTE_SHA" != "$GIT_HEAD" ]; then
    echo "local HEAD ($GIT_HEAD) does not match remote HEAD ($REMOTE_SHA) and PUSH_ON_RUN=false; aborting" >&2
    exit 2
  fi
fi

# write commit as github/sha
printf '%s' "github/$GIT_HEAD" > "$META_DIR/commit"

## Use a predefined cache dir on the remote side instead of rsyncing a local worktree.
## Remote steps (performed via ssh):
##  - clone the repo into $CACHE_DIR if missing
##  - fetch updates from origin
##  - create a detached worktree under $REMOTE_BASE for the target commit
##  - cd into the worktree and run the requested command

REMOTE_BASE="/tmp/qwex-run-$RUN_ID"
cleanup(){
  rc=$?
  echo "[qwex:ssh] cleaning up (rc=$rc)"
  # remove remote dir
  ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "rm -rf '$REMOTE_BASE'" || true
  exit $rc
}
trap cleanup EXIT

# make sure remote cache exists and create a worktree
REMOTE_PREP_CMD="set -euo pipefail; set -x; echo '[remote] using cache: $REMOTE_CACHE_DIR'; if [ ! -d \"$REMOTE_CACHE_DIR/.git\" ]; then mkdir -p \"$REMOTE_CACHE_DIR\" && git clone \"$GIT_REMOTE_URL\" \"$REMOTE_CACHE_DIR\"; else git -C \"$REMOTE_CACHE_DIR\" fetch --all --prune; fi; echo '[remote] cache list:'; ls -la \"$REMOTE_CACHE_DIR\" || true; rm -rf '$REMOTE_BASE'; git -C \"$REMOTE_CACHE_DIR\" worktree add --detach '$REMOTE_BASE' $GIT_HEAD; echo '[remote] worktree created:'; ls -la '$REMOTE_BASE' || true; cd '$REMOTE_BASE'"

# prepare remote execution body
if [ "$#" -gt 0 ]; then
  # Use the provided args as the remote command (preserve spaces/quotes)
  REMOTE_BODY="bash -lc -- \"$*\""
else
  # read script from stdin and upload as run.sh into a temp local file
  TMP_SCRIPT_LOCAL=$(mktemp)
  cat - > "$TMP_SCRIPT_LOCAL"
  REMOTE_BODY="chmod +x run.sh && ./run.sh"
fi

# full remote command: prep + (for stdin case, write upload then execute)
if [ "$#" -gt 0 ]; then
  REMOTE_EXEC_CMD="$REMOTE_PREP_CMD && $REMOTE_BODY"
  echo "[qwex:ssh] executing remotely: $REMOTE_EXEC_CMD"
  # run remote command and stream raw stdout/stderr into local logs while printing
  ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "$REMOTE_EXEC_CMD" \
    > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
  exit_code=${PIPESTATUS[0]:-$?}
else
  # For stdin-uploaded script, create the worktree remotely, then stream the script, then execute it.
  # Create the remote worktree first
  echo "[qwex:ssh] preparing remote cache and worktree on $QWEX_SSH_TARGET:$REMOTE_CACHE_DISPLAY"
  ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "$REMOTE_PREP_CMD" || {
    echo "remote prep failed" >&2
    exit 2
  }
  # upload script into the remote worktree's run.sh using ssh+cat to avoid scp/rsync dependency
  cat "$TMP_SCRIPT_LOCAL" | ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "cat > '$REMOTE_BASE/run.sh'"
  rm -f "$TMP_SCRIPT_LOCAL"
  echo "[qwex:ssh] executing remote run.sh"
  ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "cd '$REMOTE_BASE' && $REMOTE_BODY" \
    > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
  exit_code=${PIPESTATUS[0]:-$?}
fi

printf '%s' "$(now_iso)" > "$META_DIR/started_at"
printf '%s' "running" > "$META_DIR/status"

echo "[qwex:ssh] executing remotely: $REMOTE_EXEC_CMD"
# run remote command and stream raw stdout/stderr into local logs while printing
ssh -p "$QWEX_SSH_PORT" "$QWEX_SSH_TARGET" "$REMOTE_EXEC_CMD" \
  > >(tee "$LOG_DIR/stdout.log") 2> >(tee "$LOG_DIR/stderr.log" >&2)
exit_code=${PIPESTATUS[0]:-$?}

printf '%s' "$(now_iso)" > "$META_DIR/finished_at"
printf '%s' "$exit_code" > "$META_DIR/exit_code"
if [ "$exit_code" -eq 0 ]; then
  printf '%s' "succeeded" > "$META_DIR/status"
else
  printf '%s' "failed" > "$META_DIR/status"
fi

echo "[qwex:ssh] run complete: exit=$exit_code; run id=$RUN_ID"
exit $exit_code
