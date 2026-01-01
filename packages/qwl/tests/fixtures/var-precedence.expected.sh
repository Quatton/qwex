#!/usr/bin/env bash
QWEX_PREAMBLE="#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases
"

eval QWEX_PREAMBLE

@help() {
  echo "Available tasks:"
  echo "  useModuleVar"
  echo "  useTaskVar"
}

# Hash: 0xd31f6dfb57018322
useModuleVar() {
  echo "module-level"
}

# Hash: 0x2d7cc2d1c0c0413b
useTaskVar() {
  echo "task-level"
}

@main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      @help
      ;;
    "useModuleVar")
      shift
      useModuleVar "$@"
      ;;
    "useTaskVar")
      shift
      useTaskVar "$@"
      ;;
    *)
      echo "Unknown task: $1" >&2
      @help
      exit 1
      ;;
  esac
}

@main "$@"
