#!/bin/bash

# ==========================================
# Qwex Core Runtime (Micro-Kernel)
# ==========================================

# 1. Safety First: Unofficial Strict Mode
set -u  # Fail on undefined variables

# 2. Color Primitives (Graceful degradation)
if [ -t 1 ]; then
    Q_RED='\033[0;31m'
    Q_GREEN='\033[0;32m'
    Q_BLUE='\033[0;34m'
    Q_GRAY='\033[0;90m'
    Q_RESET='\033[0m'
else
    Q_RED='' Q_GREEN='' Q_BLUE='' Q_GRAY='' Q_RESET=''
fi

# 3. Structured Logging
q_log() {
    echo -e "${Q_BLUE}[QWEX]${Q_RESET} $1"
}

q_error() {
    echo -e "${Q_RED}[FAIL]${Q_RESET} $1" >&2
}

# 4. The Core Runner: "Pipefail without Pipes"
# Usage: q_run_step "Step Name" "Command String"
q_run_step() {
    local step_name="$1"
    local command_str="$2"
    local start_time=$(date +%s)

    echo -e "\n${Q_GRAY}┌── ${Q_BLUE}Step: ${step_name}${Q_RESET}"
    echo -e "${Q_GRAY}│ Executing: ${command_str}${Q_RESET}"

    # --- EXECUTION BARRIER ---
    # We use 'eval' to allow complex shell strings (pipes, redirects) 
    # inside a single step, while keeping the parent script safe.
    eval "$command_str"
    local exit_code=$?
    # -------------------------

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        echo -e "${Q_GRAY}└─ ${Q_GREEN}✔ Success${Q_GRAY} (${duration}s)${Q_RESET}"
        return 0
    else
        echo -e "${Q_GRAY}└─ ${Q_RED}✘ Failed${Q_GRAY} (Exit Code: ${exit_code})${Q_RESET}"
        # This is the "Pipefail" behavior:
        # We explicitly exit the ENTIRE script if a step fails.
        exit $exit_code
    fi
}

# 5. Assertion Helper
# Usage: q_assert "Condition Description" "[ -f some_file ]"
q_assert() {
    local desc="$1"
    local check="$2"

    if ! eval "$check"; then
        q_error "Assertion Failed: $desc"
        exit 1
    fi
}