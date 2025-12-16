#!/usr/bin/env bash

set -u

declare -gA MODULE_DEPENDENCIES_HASHSET
module:register_dependency () {
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
  declare -A seen
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
  echo -e "\n${Q_GRAY}==============================${Q_RESET}\n"
  echo -e "${Q_BLUE}Redeclaring context for a new shell boundary...${Q_RESET}\n"

  local module_name="$1"
  local dependencies=($(module:collect_dependencies "$module_name"))
  echo $(declare -f ${dependencies[@]})
}
module:register_dependency "module:include" "std:color"

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
  echo -e "[DEBUG] $1" >&2
}

module:register_dependency "log:debug" ""


std:color () {
  log:debug "Initializing std:color module"
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

  echo -e "\n${Q_GRAY}┌── ${Q_BLUE}Step: ${1}${Q_RESET}"
  echo -e "${Q_GRAY}│ Executing: ${2}${Q_RESET}"

  local start_time=$(date +%s)

  local command_str="$2"

  # --- EXECUTION BARRIER ---
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
      exit $exit_code
  fi
}
module:register_dependency "std:step" "std:color"

ssh:exec() {
  ssh csc "$@"
}
module:register_dependency "ssh:exec" ""


run() {
  std:step "Echo" "echo Hello, World!"
  std:step "Remote" "ssh:exec echo 'Remote command executed.'"
  std:step "Steps inside Remote" "ssh:exec bash -c '$(module:include "std:step"); std:step \"Inner Step\" \"echo This is an inner step executed remotely.\"'"
}
module:register_dependency "run" "std:step ssh:exec"


help() {
  echo "Usage: $0 [command]"
  echo ""
  echo "Commands:"
  echo "  run       Execute the test run sequence."
  echo "  help      Show this help message."
}

"${@:-help}"
