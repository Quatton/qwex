#!/usr/bin/env bash
QWEX_PREAMBLE="#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases
"

eval QWEX_PREAMBLE

@help() {
  echo "Available tasks:"
  echo "  helper"
  echo "  main"
}

# Hash: 0x7e7ce317d7fd2d24
helper() {
  echo "I am helper"

}

# Hash: 0xce7ddf67ab4ad20e
main() {
  docker run python:3.12 -it --rm -- "eval "$(declare -f helper)"
  helper
"

}

@main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      @help
      ;;
    "helper")
      shift
      helper "$@"
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

