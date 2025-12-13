"""Plugin system for qwex.

Plugins are referenced as "namespace/name" (e.g., "std/echo", "std/bash").
Each plugin compiles to a bash function and provides a way to invoke it.

Built-in plugins (std/*):
- std/echo: Echo a message
- std/bash: Run a raw command
- std/base: Alias for std/bash (deprecated)
- std/shell: Run inline shell script

Qwex plugins (qwex/*):
- qwex/runbook: Interactive runbook step with hints
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import shlex
import json


class Plugin(ABC):
    """Base class for plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name (e.g., 'echo')."""
        ...

    @property
    @abstractmethod
    def namespace(self) -> str:
        """Plugin namespace (e.g., 'std')."""
        ...

    @property
    def full_name(self) -> str:
        """Full plugin reference (e.g., 'std/echo')."""
        return f"{self.namespace}/{self.name}"

    @abstractmethod
    def compile_function(self) -> str:
        """Compile the plugin to a bash function definition."""
        ...

    @abstractmethod
    def compile_call(self, params: dict[str, Any]) -> str:
        """Compile a call to this plugin with given parameters."""
        ...

    def bash_function_name(self) -> str:
        """Get the bash function name for this plugin."""
        return f"__{self.namespace}__{self.name}"


class EchoPlugin(Plugin):
    """std/echo - Echo a message to stdout."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def namespace(self) -> str:
        return "std"

    def compile_function(self) -> str:
        return f"""{self.bash_function_name()}() {{
    local message="$1"
    echo "$message"
}}"""

    def compile_call(self, params: dict[str, Any]) -> str:
        message = params.get("message", "")
        # Escape for shell
        escaped = shlex.quote(str(message))
        return f"{self.bash_function_name()} {escaped}"


class BasePlugin(Plugin):
    """std/base - Run a raw command.

    Deprecated: prefer referencing as std/bash in configs.
    """

    @property
    def name(self) -> str:
        return "base"

    @property
    def namespace(self) -> str:
        return "std"

    def compile_function(self) -> str:
        return f"""{self.bash_function_name()}() {{
    local cmd="$1"
    eval "$cmd"
}}"""

    def compile_call(self, params: dict[str, Any]) -> str:
        command = params.get("command", "")
        escaped = shlex.quote(str(command))
        return f"{self.bash_function_name()} {escaped}"


class BashPlugin(BasePlugin):
    """std/bash - Run a raw command."""

    @property
    def name(self) -> str:
        return "bash"


class ShellPlugin(Plugin):
    """std/shell - Run inline shell script."""

    @property
    def name(self) -> str:
        return "shell"

    @property
    def namespace(self) -> str:
        return "std"

    def compile_function(self) -> str:
        # No function needed, we inline the script directly
        return ""

    def compile_call(self, params: dict[str, Any]) -> str:
        run = params.get("run", "")
        if isinstance(run, list):
            run = "\n".join(run)
        return str(run)


class RunbookPlugin(Plugin):
    """qwex/runbook - Interactive runbook step with hints.

    Displays a prompt, shows hint on 'h', waits for 'y' to continue.
    Optionally sends completion event to webhook.
    """

    @property
    def name(self) -> str:
        return "runbook"

    @property
    def namespace(self) -> str:
        return "qwex"

    def compile_function(self) -> str:
        return f"""{self.bash_function_name()}() {{
    local prompt="$1"
    local hint="$2"
    local webhook_url="$3"
    local webhook_body="$4"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📋 $prompt"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Commands: [h] show hint  [y] mark complete  [s] skip  [q] quit"
    echo ""
    
    while true; do
        read -p "> " -n 1 -r choice
        echo ""
        case "$choice" in
            h|H)
                echo ""
                echo "💡 Hint:"
                echo "$hint"
                echo ""
                ;;
            y|Y)
                echo "✓ Marked complete"
                if [ -n "$webhook_url" ] && [ -n "$webhook_body" ]; then
                    curl -s -X POST "$webhook_url" \\
                        -H "Content-Type: application/json" \\
                        -d "$webhook_body" > /dev/null 2>&1 || true
                fi
                break
                ;;
            s|S)
                echo "⏭ Skipped"
                break
                ;;
            q|Q)
                echo "❌ Quit"
                exit 1
                ;;
            *)
                echo "Unknown command. Use h/y/s/q"
                ;;
        esac
    done
}}"""

    def compile_call(self, params: dict[str, Any]) -> str:
        prompt = shlex.quote(str(params.get("prompt", "Step")))
        hint = shlex.quote(str(params.get("hint", "No hint available")))

        # Handle optional webhook
        on_complete = params.get("on_complete", {})
        if on_complete and isinstance(on_complete, dict):
            webhook_url = shlex.quote(str(on_complete.get("url", "")))
            webhook_body = shlex.quote(json.dumps(on_complete.get("body", {})))
        else:
            webhook_url = "''"
            webhook_body = "''"

        return (
            f"{self.bash_function_name()} {prompt} {hint} {webhook_url} {webhook_body}"
        )


# Plugin registry
_BUILTIN_PLUGINS: dict[str, Plugin] = {
    "std/echo": EchoPlugin(),
    "std/bash": BashPlugin(),
    "std/base": BasePlugin(),
    "std/shell": ShellPlugin(),
    "qwex/runbook": RunbookPlugin(),
}


def get_plugin(ref: str) -> Plugin:
    """Get a plugin by its reference (e.g., 'std/echo')."""
    if ref in _BUILTIN_PLUGINS:
        return _BUILTIN_PLUGINS[ref]
    raise ValueError(f"Unknown plugin: {ref}")


def list_builtin_plugins() -> list[str]:
    """List all built-in plugin references."""
    return list(_BUILTIN_PLUGINS.keys())
