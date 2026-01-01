#!/usr/bin/env bash
set -euo pipefail

@help() {
  echo "Available tasks:"
  echo "  greet"
  echo "  logAndGreet"
}

# Hash: 0xe61156d0d267aad2
greet() {
  echo "Hello"
}

# Hash: 0x81b5936506d82f93
logAndGreet() {
  echo "[LOG] INFO: $1"
echo "Hello"

}

@main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      @help
      ;;
    "greet")
      shift
      greet "$@"
      ;;
    "logAndGreet")
      shift
      logAndGreet "$@"
      ;;
    *)
      echo "Unknown task: $1" >&2
      @help
      exit 1
      ;;
  esac
}

@main "$@"
