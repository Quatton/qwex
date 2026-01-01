#!/usr/bin/env bash
QWEX_PREAMBLE="#!/usr/bin/env bash
set -euo pipefail
shopt -s expand_aliases
"

eval QWEX_PREAMBLE

@help() {
  echo "Available tasks:"
  echo "  test"
}

# Hash: 0x539491bc200ad187
test() {
  echo "Hello World" > "/tmp/test/output.txt"

}

@main() {
  case "${1:-}" in
    ""|"-h"|"--help"|"help")
      @help
      ;;
    "test")
      shift
      test "$@"
      ;;
    *)
      echo "Unknown task: $1" >&2
      @help
      exit 1
      ;;
  esac
}

@main "$@"
