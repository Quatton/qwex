#!/usr/bin/env bash
set -euo pipefail

@help() {
  echo "Available tasks:"
  echo "  helper"
  echo "  main"
}

# Hash: 0xcedf45010064ca04
helper() {
  echo "Hello from helper"
}

# Hash: 0xf5abfe83a4480c4a
main() {
  echo "Inlined: echo "Hello from helper""

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
