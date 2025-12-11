#!/usr/bin/env bash
# trace.sh - minimal runner that records run metadata and streams output
# Usage:
#   .qwex/_internal/compiled/trace.sh <command> [args...]
# or: cat script.sh | .qwex/_internal/compiled/trace.sh

set -euo pipefail

# --- helpers ---
now_iso(){ date --iso-8601=seconds 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ"; }
ensure_dir(){ mkdir -p "$@"; }
sanitize_ns(){ # lowercase, replace non-alnum with -, collapse dashes
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g'
}

# --- determine namespace and run id ---
NAMESPACE=${QWEX_NAMESPACE:-$(basename "$PWD")}
NAMESPACE=$(sanitize_ns "$NAMESPACE")
TS=$(date +%Y%m%dT%H%M%S%N)
RAND=$(printf '%04x%04x' $RANDOM $RANDOM)
RUN_ID="${NAMESPACE}-${TS}-${RAND}"

QWEX_RUNS_DIR=${QWEX_RUNS_DIR:-.qwex/_internal/runs}
RUN_DIR="$QWEX_RUNS_DIR/$RUN_ID"
META_DIR="$RUN_DIR/meta"
LOG_DIR="$RUN_DIR/logs"

ensure_dir "$META_DIR" "$LOG_DIR"

# created_at
created_at=$(now_iso)
printf '%s' "$created_at" > "$META_DIR/created_at"

# record started_at, run command, capture logs
started_at=""
finished_at=""
exit_code=0
status="pending"

run_cmd_and_capture(){
  # prepare command: either args or stdin
  if [ "$#" -gt 0 ]; then
    # run provided command and args
    cmd=("$@")
    # run in subshell, capture stdout/stderr to files while streaming
    started_at=$(now_iso)
    printf '%s' "$started_at" > "$META_DIR/started_at"
    status="running"
    printf '%s' "$status" > "$META_DIR/status"

    # run the command, teeing stdout and stderr
    (
      set +e
      "${cmd[@]}" > >(
        tee "$LOG_DIR/stdout.log"
      ) 2> >(
        tee "$LOG_DIR/stderr.log" >&2
      )
      exit_code=$?
      return $exit_code
    )
    exit_code=$?
  else
    # read script from stdin into temp file and execute it
    tmp_script=$(mktemp)
    cat - > "$tmp_script"
    chmod +x "$tmp_script"
    started_at=$(now_iso)
    printf '%s' "$started_at" > "$META_DIR/started_at"
    status="running"
    printf '%s' "$status" > "$META_DIR/status"

    (
      set +e
      bash "$tmp_script" > >(
        tee "$LOG_DIR/stdout.log"
      ) 2> >(
        tee "$LOG_DIR/stderr.log" >&2
      )
      exit_code=$?
      return $exit_code
    )
    exit_code=$?
    rm -f "$tmp_script"
  fi

  finished_at=$(now_iso)
  printf '%s' "$finished_at" > "$META_DIR/finished_at"
  printf '%s' "$exit_code" > "$META_DIR/exit_code"
  if [ "$exit_code" -eq 0 ]; then
    status="succeeded"
  else
    status="failed"
  fi
  printf '%s' "$status" > "$META_DIR/status"
}

run_cmd_and_capture "$@"

exit $exit_code
