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
        emitted_fns: set[str] = set()

        # Helper to compile module tasks recursively
        def emit_module_tasks(mod: Module, mod_env: Dict[str, Any]):
            for task in mod.tasks.values():
                fn = self._compile_task(mod.name, task, mod_env)
                if fn.name not in emitted_fns:
                    emitted_fns.add(fn.name)
                    functions.append(fn)

            # Recursively emit imported module tasks with their own env
            for mod_ref_name in mod.modules:
                loaded = self.resolver._module_cache.get(mod_ref_name)
                if loaded and mod_ref_name in mod_env:
                    sub_env = mod_env[mod_ref_name]
                    emit_module_tasks(loaded, sub_env)

        # Start with root module
        emit_module_tasks(module, env_tree)

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

        # Build task-local context: flattened env + task vars
        task_context = dict(env_tree)
        if task.vars:
            task_context.update(task.vars)

        # Handle `uses/with` inlining
        if task.uses:
            body = self._compile_uses_with(
                task.uses, task.with_, env_tree, task_context
            )
        else:
            # Render the body with Jinja
            body = self._render(task.run or "", task_context)

        # Detect dependencies from rendered body (look for module:task patterns)
        deps = self._detect_dependencies(body)

        return BashFunction(name=fn_name, body=body, dependencies=list(deps))

    def _compile_uses_with(
        self,
        uses: str,
        with_items: list,
        env_tree: Dict[str, Any],
        task_context: Dict[str, Any],
    ) -> str:
        """Compile a uses/with block by inlining and expanding the referenced task.

        Args:
            uses: Reference to task (e.g., "steps.step" or "log.debug").
            with_items: List of items to substitute (positional args or dict mappings).
            env_tree: Full environment tree.
            task_context: Task-local context for rendering.

        Returns:
            Inlined and expanded bash body.
        """
        # Parse the uses reference: module.task or just module:task canonical
        parts = uses.split(".")
        if len(parts) != 2:
            # Try splitting by colon (canonical name)
            parts = uses.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid uses reference: {uses} (expected module.task)")

        module_name, task_name = parts

        # Lookup the referenced task in env_tree
        # With flattened env, module_name should be a dict in env_tree
        if module_name not in env_tree:
            raise ValueError(f"Module '{module_name}' not found in modules")
        
        module_env = env_tree[module_name]
        
        # In flattened env, task name is a direct key in module_env
        if task_name not in module_env:
            raise ValueError(f"Task '{task_name}' not found in module '{module_name}'")

        # Get the canonical name (e.g., "steps:step")
        canonical_name = module_env[task_name]

        # Build a list of inlined commands, one per with_item
        lines = []

        for item in with_items:
            # If item is a dict, it's a set of var overrides
            if isinstance(item, dict):
                # We need to render the task with these overrides
                # But 'uses' implies we are calling the task or inlining it?
                # The spec says:
                # - string item: positional arg passed to command
                # - dict item: var overrides? Or named args?
                
                # In the old implementation:
                # dict item with 'run' -> inline run command
                # string item -> positional arg
                
                # With the "steps.compose" pattern:
                # uses: steps.compose
                # with:
                #   - name: "Step 1"
                #     run: "echo hi"
                
                # If the item is a dict, we probably want to treat it as variables 
                # available to the inlined task, OR if it's the steps.compose pattern,
                # it might be special handling. 
                
                # But generic `uses` usually means "call this task".
                # If `uses` points to a task that expects args (legacy), we pass them.
                # Now that args are gone, we just have vars.
                
                # If the user provides a dict in `with`, it merges into vars for that call.
                # BUT, we are generating bash script. We can't easily "call with vars" 
                # without subshells or var assignments.
                
                # However, the previous implementation did:
                # if dict has 'run': render run and append.
                # This seems specific to the 'steps' pattern where `with` items are steps.
                
                # Let's preserve the existing logic as much as possible but adapted.
                # Existing:
                # if dict: run_cmd = item.get("run"); render(run_cmd, context)
                
                run_cmd = item.get("run")
                if run_cmd:
                     rendered_cmd = self._render(run_cmd, task_context)
                     lines.append(rendered_cmd)
                else:
                    # Generic dict item - maybe just vars? 
                    # If it's just vars, we can't easily inline it unless it's a template?
                    # For now, let's assume it's the steps pattern or we might need to revisit.
                    pass

            elif isinstance(item, str):
                # Simple string: treat as positional arg to the referenced task
                lines.append(f"{canonical_name} {item}")
            else:
                # Default: render as is
                rendered = self._render(str(item), task_context)
                lines.append(rendered)

        return "\n".join(lines)

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
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*)\b"
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
