#!/usr/bin/env bash

set -u

module:register_dependency () {
  declare -gA MODULE_DEPENDENCIES_HASHSET
  local module_name="$1"
  local deps="$2"
  MODULE_DEPENDENCIES_HASHSET["$module_name"]="$deps"
}
module:register_dependency "module:register_dependency" ""

module:collect_dependencies () {
  # traverse through dependencies recursively
  local module_name="$1"
  local deps="${MODULE_DEPENDENCIES_HASHSET[$module_name]}"
  local result=()
  for dep in $deps; do
    result+=($(module:collect_dependencies "$dep"))
    result+=("$dep")
  done
  # remove duplicates
  local unique_result=()
  local -A seen
  for item in "${result[@]}"; do
    if [[ -z "${seen[$item]+x}" ]]; then
      seen[$item]=1
      unique_result+=("$item")
    fi
  done
  echo "${unique_result[@]}"  
}
module:register_dependency "module:collect_dependencies" "log:debug"

module:include() {
  std:once "std:color"
  log:debug "Initializing module: $@"

  local unique_result=()
  local -A seen

  local dependencies=($(module:collect_dependencies "$@"))
  dependencies+=("$@")
  for item in "${dependencies[@]}"; do
    if [[ -z "${seen[$item]+x}" ]]; then
      seen[$item]=1
      unique_result+=("$item")
    fi
  done

  log:debug "${Q_BLUE}Redeclaring context for a new shell boundary...${Q_RESET}"

  declare -f "${unique_result[@]}"
}
module:register_dependency "module:include" "std:color log:debug"

std:once () {
  declare -gA STD_ONCE_HASHSET
  local key="$1"
  if [[ -z "${STD_ONCE_HASHSET[$key]+x}" ]]; then
    STD_ONCE_HASHSET[$key]=1
    eval "$key"
  else
    true
  fi
}
module:register_dependency "std:once" ""

log:debug() {
  if [ "${DEBUG:-0}" -eq 0 ]; then
    return
  fi
  echo -e "$*" >&2
}

module:register_dependency "log:debug" ""


std:color () {
  if [ -t 1 ]; then
    Q_RED='\033[0;31m'
    Q_GREEN='\033[0;32m'
    Q_BLUE='\033[0;34m'
    Q_GRAY='\033[0;90m'
    Q_RESET='\033[0m'
  else
      Q_RED='' Q_GREEN='' Q_BLUE='' Q_GRAY='' Q_RESET=''
  fi
}
module:register_dependency "std:color" "std:once"

std:step () {
  std:once "std:color"

  log:debug "\n${Q_GRAY}┌── ${Q_BLUE}Step: ${1}${Q_RESET}"

  local command_str="$2"
  local truncated_command_str=$(echo "$command_str" | head -c 60)
  log:debug "${Q_GRAY}│ Executing: ${truncated_command_str}${Q_RESET}"

  local start_time=$(date +%s)


  # --- EXECUTION BARRIER ---
  eval "$command_str"
  local exit_code=$?
  # -------------------------

  local end_time=$(date +%s)
  local duration=$((end_time - start_time))

  if [ $exit_code -eq 0 ]; then
      log:debug "${Q_GRAY}└─ ${Q_GREEN}✔ Success${Q_GRAY} (${duration}s)${Q_RESET}"
      return 0
  else
      log:debug "${Q_GRAY}└─ ${Q_RED}✘ Failed${Q_GRAY} (Exit Code: ${exit_code})${Q_RESET}"
      exit $exit_code
  fi
}
module:register_dependency "std:step" "std:color log:debug"

ssh:exec() {
  ssh csc "$@"
}
module:register_dependency "ssh:exec" ""


run() {
  std:step "Echo" "echo Hello, World!"
  std:step "Remote" "ssh:exec echo 'Remote command executed.'"
  std:step "Steps inside Remote" "ssh:exec bash -s << 'EOF'
$(module:include "std:step")
std:step 'Remote Step' 'echo This is a step executed on the remote server.'
std:step 'I can show you by uname -a' 'uname -a'
EOF"
}
module:register_dependency "run" "std:step ssh:exec"


help() {
  echo "Usage: $0 [command]"
  echo ""
  echo "Commands:"
  echo "  run       Execute the test run sequence."
  echo "  help      Show this help message."
}
module:register_dependency "help" "log:debug"

"${@:-help}"

