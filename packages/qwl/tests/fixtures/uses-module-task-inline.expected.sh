#!/usr/bin/env bash
QWEX_PREAMBLE="#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases
"

eval QWEX_PREAMBLE

@help() {
  echo "Available tasks:"
  echo "  main"
}

# Hash: 0x5a2c2d0d860727de
main() {
  echo "From submodule"

}

@main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      @help
      ;;
    "main")
      shift
      main "$@"
      ;;
    *)
      echo "Unknown task: $1" >&2
      @help
      exit 1
      ;;
  esac
}

@main "$@"
