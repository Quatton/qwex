#!/usr/bin/env bash)


__ssh() {
  ssh csc "$@"
}
SSH_SOURCE="$(declare -f __ssh)"

__srun() {
  sbatch --mem=4G --cpus-per-task=1 --time=01:00:00 --parsable --wrap="$*"
}
SRUN_SOURCE="$(declare -f __srun)"

__trace(){ echo "running command: $*"; eval time "$@"; echo "command finished: $*"; }
TRACE_SOURCE="$(declare -f __trace)"

__trace $@

__ssh bash -s -- "$@" << EOF
${TRACE_SOURCE}
${SRUN_SOURCE}

__trace "__srun \$@"
EOF