#!/usr/bin/env bash

set -euo pipefail

function hello() {
    echo "Hello from test2.sh"
}
alias hello_world=hello

hello

hello_world