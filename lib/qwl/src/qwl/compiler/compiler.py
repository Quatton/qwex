"""Compiler - transforms resolved AST into BashScript IR."""

from pathlib import Path
from typing import Dict, Any, Optional, Set
import re

from qwl.ast.spec import Module, Task
from qwl.compiler.spec import BashFunction, BashScript
from qwl.compiler.resolver import Resolver


class Compiler:
    """Compiles Module AST to BashScript IR."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize compiler with optional base directory for module resolution.

        Args:
            base_dir: Base directory for resolving relative module paths.
        """
        self.base_dir = base_dir or Path.cwd()
        self.resolver = Resolver(self.base_dir)

    def compile(self, module: Module) -> BashScript:
        """Compile a Module into a BashScript IR with full module resolution.

        Args:
            module: The root module to compile.

        Returns:
            BashScript IR ready for rendering to text.
        """
        # Resolve all modules and build environment tree
        env_tree = self.resolver.resolve(module)

        # Compile all tasks from root module
        functions = []
        task_names = list(module.tasks.keys())

        # Flatten and compile each task
        for task_name, task in module.tasks.items():
            fn = self._compile_task(module.name, task, env_tree)
            functions.append(fn)

        # Auto-generate help function
        functions.append(self._compile_help(task_names))

        script = BashScript(functions=functions, available_tasks=task_names)
        return script

    def _compile_task(
        self, module_name: str, task: Task, env_tree: Dict[str, Any]
    ) -> BashFunction:
        """Compile a single Task to a BashFunction.

        Args:
            module_name: The parent module's name (for namespacing).
            task: The Task to compile.
            env_tree: Full environment tree from resolver.

        Returns:
            BashFunction with rendered body and dependencies detected.
        """
        fn_name = f"{module_name}:{task.name}"

        # Build task-local context: merge task vars and args
        task_context = dict(env_tree)  # Start with full env tree
        task_vars = task.vars if isinstance(task.vars, dict) else {}
        task_context["vars"] = {
            **env_tree.get("vars", {}),
            **task_vars,
        }

        # Build args context (renders args to bash var references)
        args_context = {}
        for i, arg in enumerate(task.args, 1):
            if arg.positional > 0:
                args_context[arg.name] = f"${{{arg.positional}:-{arg.default or ''}}}"
            else:
                args_context[arg.name] = f"${{{arg.name.upper()}:-{arg.default or ''}}}"
        task_context["args"] = args_context

        # Render the body with Jinja
        body = self._render(task.run or "", task_context)

        # Detect dependencies from rendered body (look for module:task patterns)
        deps = self._detect_dependencies(body)

        return BashFunction(name=fn_name, body=body, dependencies=list(deps))

    def _render(self, template: str, context: Dict[str, Any]) -> str:
        """Render a Jinja template string with context.

        Args:
            template: Jinja template string.
            context: Variables to render with.

        Returns:
            Rendered string.
        """
        from jinja2 import Environment

        env = Environment()
        tmpl = env.from_string(template)
        return tmpl.render(**context)

    def _detect_dependencies(self, body: str) -> Set[str]:
        """Detect bash function dependencies from rendered body.

        Looks for canonical function names like 'module:task' in the body.

        Args:
            body: Rendered bash function body.

        Returns:
            Set of canonical function names (e.g., {'log:debug', 'steps:step'}).
        """
        # Match pattern: word:word (module:task)
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*)\b'
        matches = re.findall(pattern, body)
        return set(matches)

    def _compile_help(self, task_names: list[str]) -> BashFunction:
        """Create a help function listing available tasks."""
        lines = [
            'echo "Usage: $0 [task]"',
            'echo ""',
            'echo "Tasks:"',
        ]
        for task_name in task_names:
            lines.append(f'echo "  {task_name}"')

        body = "\n".join(lines)
        return BashFunction(name="help", body=body, dependencies=[])

