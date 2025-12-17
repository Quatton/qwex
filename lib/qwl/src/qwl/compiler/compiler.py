"""Compiler - transforms resolved AST into BashScript IR."""

from typing import Dict, Any, Optional

from qwl.ast.spec import Module, Task
from qwl.compiler.spec import BashFunction, BashScript


class Compiler:
    """Compiles Module AST to BashScript IR."""

    def __init__(self):
        pass

    def compile(
        self, module: Module, context: Optional[Dict[str, Any]] = None
    ) -> BashScript:
        """Compile a Module into a BashScript IR.

        Args:
            module: The parsed Module AST.
            context: Optional context dict for Jinja rendering (vars, modules, etc.)

        Returns:
            BashScript IR ready for rendering to text.
        """
        context = context or {}

        # Merge module vars into context
        ctx = {
            "vars": {**module.vars, **context.get("vars", {})},
            "modules": context.get("modules", {}),
        }

        functions = []
        for task_name, task in module.tasks.items():
            fn = self._compile_task(module.name, task, ctx)
            functions.append(fn)

        functions.append(self._compile_help(module))

        return BashScript(functions=functions)

    def _compile_task(
        self, module_name: str, task: Task, context: Dict[str, Any]
    ) -> BashFunction:
        """Compile a single Task to a BashFunction.

        Args:
            module_name: The parent module's name (for namespacing).
            task: The Task to compile.
            context: Context for Jinja rendering.

        Returns:
            BashFunction with rendered body.
        """
        # Function name: module_name:task_name
        fn_name = f"{module_name}:{task.name}"

        # Render the body with Jinja
        body = self._render(task.run or "", context)

        # Dependencies will be detected later (for now, empty)
        deps: list[str] = []

        return BashFunction(name=fn_name, body=body, dependencies=deps)

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

    def _compile_help(self, module: Module) -> BashFunction:
        """Create a simple help function listing available tasks."""

        lines = [
            'echo "Usage: $0 [task]"',
            'echo ""',
            'echo "Tasks:"',
        ]
        for task_name in module.tasks:
            lines.append(f'echo "  {task_name}"')

        body = "\n".join(lines)
        return BashFunction(name="help", body=body, dependencies=[])
