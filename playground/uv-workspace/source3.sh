QWEX_PREAMBLE="set -euo pipefail
shopt -s expand_aliases
ORIGINAL_PWD=$(pwd)"
steps:log:_should_log () 
{ 
    local msg_level="${1:-INFO}";
    local current_level="${LOG_LEVEL:-INFO}";
    function _to_num () 
    { 
        case "${1:-}" in 
            TRACE | trace | 1)
                echo 1
            ;;
            DEBUG | debug | 2)
                echo 2
            ;;
            INFO | info | 3)
                echo 3
            ;;
            WARN | warn | WARNING | warning | 4)
                echo 4
            ;;
            ERROR | error | 5)
                echo 5
            ;;
            *)
                echo 3
            ;;
        esac
    };
    local msg_num=$(_to_num "$msg_level");
    local current_num=$(_to_num "$current_level");
    [ "$msg_num" -ge "$current_num" ]
}
steps:log:_timestamp () 
{ 
    date '+%Y-%m-%d %H:%M:%S'
}
steps:log:debug () 
{ 
    if steps:log:_should_log 2; then
        printf '%s [38;2;128;128;128m[DEBUG][38;2;255;255;255m %s\n' "$(steps:log:_timestamp)" "$1" 1>&2;
    fi
}
steps:step () 
{ 
    local description=${1:-""};
    shift;
    local command=${*:-""};
    printf '%s\n' "[38;2;128;128;128m┌──[38;2;255;255;255m [38;2;0;0;255mStep:[38;2;255;255;255m $description" 1>&2;
    local truncated_command="${command:0:60}";
    if [ "${#command}" -gt 60 ]; then
        truncated_command="${truncated_command}...";
    fi;
    steps:log:debug "[38;2;128;128;128m│ Executing:[38;2;255;255;255m $truncated_command";
    local start_time=$(date +%s);
    local exit_code=$?;
    if eval "$command"; then
        exit_code=0;
    else
        exit_code=$?;
    fi;
    local end_time=$(date +%s);
    local duration=$((end_time - start_time));
    if [ $exit_code -eq 0 ]; then
        printf '%s\n' "[38;2;128;128;128m└─[38;2;255;255;255m [38;2;0;128;0m✔ Success[38;2;255;255;255m [38;2;128;128;128m(${duration}s)[38;2;255;255;255m" 1>&2;
    else
        printf '%s\n' "[38;2;128;128;128m└─[38;2;255;255;255m [38;2;255;0;0m✘ Failed[38;2;255;255;255m [38;2;128;128;128m(Exit Code: ${exit_code})[38;2;255;255;255m" 1>&2;
        return $exit_code;
    fi
}
steps:log:error () 
{ 
    if steps:log:_should_log 5; then
        printf '%s [38;2;255;0;0m✘[38;2;255;255;255m %s\n' "$(steps:log:_timestamp)" "$1" 1>&2;
    fi
}
log:info () 
{ 
    if steps:log:_should_log 3; then
        printf '%s [38;2;0;0;255mℹ[38;2;255;255;255m %s\n' "$(steps:log:_timestamp)" "$1" 1>&2;
    fi
}
log:warn () 
{ 
    if steps:log:_should_log 4; then
        printf '%s [38;2;255;255;0m⚠[38;2;255;255;255m %s\n' "$(steps:log:_timestamp)" "$1" 1>&2;
    fi
}
test () 
{ 
    local failed=false;
    local failed_desc="";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Create temp directory " "mkdir -p ./uv-workspace-demo"; then
            failed=true;
            failed_desc="Create temp directory";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Initialize uv project " "uv init ./uv-workspace-demo
"; then
            failed=true;
            failed_desc="Initialize uv project";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Run hello.py " "cd ./uv-workspace-demo
uv run hello.py
"; then
            failed=true;
            failed_desc="Run hello.py";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = true ]; then
        steps:log:error "Step \"${failed_desc}\" failed. Exiting with error.";
        return 1;
    fi
}
clean () 
{ 
    if [ -d "./uv-workspace-demo" ]; then
        rm -rf "./uv-workspace-demo";
        log:info "Cleaned up temp directory: ./uv-workspace-demo";
    else
        log:warn "No temp directory info found for cleanup.";
    fi
}
all () 
{ 
    local failed=false;
    local failed_desc="";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Clean up " "clean"; then
            failed=true;
            failed_desc="Clean up";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Run tests " "test"; then
            failed=true;
            failed_desc="Run tests";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "All done " "log:info 'UV workspace test completed.'"; then
            failed=true;
            failed_desc="All done";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "false" = "true" ]; then
        if ! steps:step "Intentional failure step " "steps:log:error 'This is a simulated failure.'; return 1"; then
            failed=true;
            failed_desc="Intentional failure step";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = false ] || [ "true" = "true" ]; then
        if ! steps:step "Final cleanup (always)" "clean"; then
            failed=true;
            failed_desc="Final cleanup";
        fi;
    fi;
    cd "$ORIGINAL_PWD";
    if [ "$failed" = true ]; then
        steps:log:error "Step \"${failed_desc}\" failed. Exiting with error.";
        return 1;
    fi
}
@main () 
{ 
    case "${1:-}" in 
        "" | "-h" | "--help" | "help")
            @help
        ;;
        "test")
            shift;
            test "$@"
        ;;
        "clean")
            shift;
            clean "$@"
        ;;
        "all")
            shift;
            all "$@"
        ;;
        *)
            echo "Unknown task: $@. Executing as a script." 1>&2;
            eval "$@"
        ;;
    esac
}
@help () 
{ 
    echo "Available tasks:";
    echo "  test - Test uv workspace creation and execution with steps.compose";
    echo "  clean - Clean up temp directory created during test";
    echo "  all - Test from clean state"
}
@source () 
{ 
    echo "QWEX_PREAMBLE=\"set -euo pipefail
shopt -s expand_aliases
ORIGINAL_PWD=\$(pwd)\"";
    declare -f steps:log:_should_log steps:log:_timestamp steps:log:debug steps:step steps:log:error log:info log:warn test clean all @main @help @source;
    echo "@main \$@"
}
@main $@
