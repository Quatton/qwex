#!/usr/bin/env bash
# noop.sh - minimal "no-op" runner for qwex
# Usage:
#   .qwex/runners/noop.sh <command> [args...]
# or: cat script.sh | .qwex/runners/noop.sh

set -euo pipefail

if [ "$#" -gt 0 ]; then
  # Execute provided command and replace shell
  exec "$@"
else
  # If no args, read command from stdin and execute it
  if [ -t 0 ]; then
    echo "Usage: $(basename "$0") <command> [args...]" >&2
    echo "Or pipe a script into stdin: cat script.sh | $(basename "$0")" >&2
    exit 2
  fi

  cmd=$(cat -)
  # Run the piped script/command in bash so it has a predictable environment
  bash -c "$cmd"
fi
