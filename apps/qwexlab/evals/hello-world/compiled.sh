#!/bin/bash

# ═══════════════════════════════════════════════════════════
# QWEX KERNEL - Micro-runtime for task execution
# ═══════════════════════════════════════════════════════════

# Safety: fail on undefined variables
set -u

# Color support (graceful degradation for non-TTY)
if [ -t 1 ]; then
    __Q_RED='\033[0;31m'
    __Q_GREEN='\033[0;32m'
    __Q_BLUE='\033[0;34m'
    __Q_GRAY='\033[0;90m'
    __Q_RESET='\033[0m'
else
    __Q_RED='' __Q_GREEN='' __Q_BLUE='' __Q_GRAY='' __Q_RESET=''
fi

# Core step runner with timing and error handling
q_run_step() {
    local step_name="$1"
    local command_str="$2"
    local start_time=$(date +%s)

    echo -e "\n${__Q_GRAY}┌── ${__Q_BLUE}Step: ${step_name}${__Q_RESET}"
    echo -e "${__Q_GRAY}│ ${command_str}${__Q_RESET}"

    # Execute with eval to support complex shell strings
    eval "$command_str"
    local exit_code=$?

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        echo -e "${__Q_GRAY}└─ ${__Q_GREEN}✔ Success${__Q_GRAY} (${duration}s)${__Q_RESET}"
        return 0
    else
        echo -e "${__Q_GRAY}└─ ${__Q_RED}✘ Failed${__Q_GRAY} (exit: ${exit_code})${__Q_RESET}"
        exit $exit_code
    fi
}

# Logging helpers
q_log() { echo -e "${__Q_BLUE}[qwex]${__Q_RESET} $1"; }
q_error() { echo -e "${__Q_RED}[qwex]${__Q_RESET} $1" >&2; }

# ═══════════════════════════════════════════════════════════
# QWEX CONTEXT - Embedded execution context
# ═══════════════════════════════════════════════════════════
__QWEX_RUN_ID="20251213_180717_e1b6bc49"
__QWEX_TASK="eval"
export QWEX_HOME="/Users/quatton/Documents/GitHub/qwex/apps/qwexlab/evals/hello-world"

# ═══════════════════════════════════════════════════════════
# QWEX ENTRYPOINT - Task execution
# ═══════════════════════════════════════════════════════════
__qwex_main() {
    q_log "run_id: $__QWEX_RUN_ID"
    q_log "task: $__QWEX_TASK"

    q_run_step 'Create eval directory' 'mkdir -p $QWEX_HOME/examples/qwex-eval'
    q_run_step 'Initialize qwex project inside eval' 'cd $QWEX_HOME/examples/qwex-eval && qwex init'
    q_run_step 'Run echo hello via qwex' 'cd $QWEX_HOME/examples/qwex-eval && qwex run "echo hello from child qwex"'
    q_run_step 'Print parent QWEX_HOME' 'echo "Parent QWEX_HOME is $QWEX_HOME"'
    q_run_step 'Verify child sees its own QWEX_HOME' 'cd $QWEX_HOME/examples/qwex-eval
qwex run '\''echo "Child QWEX_HOME is $QWEX_HOME"'\'''
}

__qwex_main "$@"
