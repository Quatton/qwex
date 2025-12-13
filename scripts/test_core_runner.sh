#!/usr/bin/env bash

# Test script for qwex core runner
# Sources scripts/core.sh which provides q_run_step

set -euo pipefail

# Locate this script's directory and source core.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/core.sh"

q_run_step "Echo 1" 'echo 1'
q_run_step "Echo 2" 'echo 2'
q_run_step "Failing step" 'ls /nonexistent/this-should-fail'
q_run_step "Echo 3" 'echo 3'