#!/usr/bin/env bash
set -euo pipefail

slurm__sbatch() {
    sbatch --job-name=hello_world \
           --output=hello_world.out \
           --error=hello_world.err \
           --time=01:00:00 \
           --cpus-per-task=1 \
           --mem=1G \
           --wrap="${1:-"echo 'Hello, World!'"}"
}

ssh__exec() {
    ssh csc "$@"
}

remote_slurm() {
    ssh__exec bash -s -- "$@" << REMOTE_EOF
    $(declare -f slurm__sbatch)
    slurm__sbatch "\$@"
    REMOTE_EOF
}

"$@"
