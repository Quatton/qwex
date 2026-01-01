#!/usr/bin/env bash
set -euo pipefail

__qwl_help() {
  echo "Available tasks:"
  echo "  sayHello"
  echo "  build"
  echo "  test"
}

# Hash: 6168453506806372058
sayHello() {
  echo "Hello, World!"
}

# Hash: 16928838612882756313
build() {
  npm run build
}

# Hash: 7494668568546972098
test() {
  npm test
}

__qwl_main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      __qwl_help
      ;;
    "sayHello")
      shift
      sayHello "$@"
      ;;
    "build")
      shift
      build "$@"
      ;;
    "test")
      shift
      test "$@"
      ;;
    *)
      echo "Unknown task: $1" >&2
      __qwl_help
      exit 1
      ;;
  esac
}

__qwl_main "$@"
