"""Compiler IR spec - Bash script intermediate representation."""

from dataclasses import dataclass, field
from typing import List


DEFAULT_PREAMBLE = "#!/usr/bin/env bash\n\nset -u"

MODULE_HEADER = """
module:register_dependency () {
    declare -gA MODULE_DEPENDENCIES_HASHSET
    local module_name="$1"
    local deps="$2"
    MODULE_DEPENDENCIES_HASHSET["$module_name"]="$deps"
}
module:register_dependency "module:register_dependency" ""

module:collect_dependencies () {
    local module_name="$1"
    local deps="${MODULE_DEPENDENCIES_HASHSET[$module_name]}"
    local result=()
    for dep in $deps; do
        result+=($(module:collect_dependencies "$dep"))
        result+=("$dep")
    done
    local unique_result=()
    local -A seen
    for item in "${result[@]}"; do
        if [[ -z "${seen[$item]+x}" ]]; then
            seen[$item]=1
            unique_result+=("$item")
        fi
    done
    echo "${unique_result[@]}"  
}
module:register_dependency "module:collect_dependencies" ""

module:include() {
    local unique_result=()
    local -A seen

    local dependencies=($(module:collect_dependencies "$@"))
    dependencies+=("$@")
    for item in "${dependencies[@]}"; do
        if [[ -z "${seen[$item]+x}" ]]; then
            seen[$item]=1
            unique_result+=("$item")
        fi
    done

    declare -f "${unique_result[@]}"
}
module:register_dependency "module:include" ""
"""


@dataclass
class BashFunction:
    """A single bash function definition."""

    name: str  # e.g., "hello-world:greet"
    body: str  # rendered function body
    dependencies: List[str] = field(
        default_factory=list
    )  # e.g., ["log:debug", "steps:step"]
    description: str = ""  # optional description


@dataclass
class BashScript:
    """Complete bash script IR."""

    preamble: str = DEFAULT_PREAMBLE
    header: str = MODULE_HEADER
    functions: List[BashFunction] = field(default_factory=list)
    available_tasks: List[str] = field(
        default_factory=list
    )  # list of task names for help
    entrypoint: str = 'if [ $# -eq 0 ]; then help; else "$@"; fi'
