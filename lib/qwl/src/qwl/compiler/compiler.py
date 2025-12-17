"""Compiler - transforms resolved AST into BashScript IR."""

from pathlib import Path
from typing import Dict, Any, Optional, Set, List, Tuple
import re

from qwl.ast.spec import Module, Task
from qwl.compiler.spec import BashFunction, BashScript
from qwl.compiler.resolver import Resolver


from collections import deque
import hashlib


class Compiler:
    """Compiles Module AST to BashScript IR."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize compiler with optional base directory for module resolution.

        Args:
            base_dir: Base directory for resolving relative module paths.
        """
        self.base_dir = base_dir or Path.cwd()
        self.resolver = Resolver(self.base_dir)

    def compile(
        self, module: Module, presets: Optional[List[str]] = None
    ) -> BashScript:
        """Compile a Module into a BashScript IR with full module resolution.

        Phase 2 algorithm:
        1. Apply presets (or defaults if no presets specified)
        2. Resolve modules and build env tree (eager for now)
        3. BFS from root tasks to discover reachable dependencies
        4. Compile only reachable tasks with canonical aliasing
        5. Body-hash deduplication to avoid emitting duplicate functions

        Args:
            module: The root module to compile.
            presets: List of preset names to apply. If None, uses module.defaults.

        Returns:
            BashScript IR ready for rendering to text.
        """
        # Phase 4: Apply presets and includes
        module = self._apply_presets_and_includes(module, presets)

        # Resolve all modules and build environment tree
        env_tree = self.resolver.resolve(module)

        # Phase 2: BFS traversal from root tasks
        task_names = list(module.tasks.keys())
        functions = self._compile_with_bfs(module, env_tree, task_names)

        # Auto-generate help function
        functions.append(self._compile_help(task_names))

        script = BashScript(functions=functions, available_tasks=task_names)
        return script

    def _apply_presets_and_includes(
        self, module: Module, presets: Optional[List[str]] = None
    ) -> Module:
        """Apply presets and includes to a module.

        Order of application:
        1. Load and merge base includes (module.includes)
        2. Determine active presets (presets arg or module.defaults)
        3. For each preset, load its includes then apply its vars/tasks/modules
        4. Module's own vars/tasks/modules override everything

        Args:
            module: The original module.
            presets: List of preset names to apply. If None, uses module.defaults.

        Returns:
            A new Module with presets and includes applied.
        """
        # Start with empty base
        merged_vars: Dict[str, Any] = {}
        merged_tasks: Dict[str, Task] = {}
        merged_modules: Dict[str, Any] = {}

        # 1. Load and merge base includes (these are the lowest priority)
        for include_path in module.includes:
            included = self._load_include(include_path)
            merged_vars.update(included.vars)
            merged_tasks.update(included.tasks)
            merged_modules.update(included.modules)

        # 2. Determine active presets
        active_presets = presets if presets is not None else module.defaults

        # 3. Apply each preset in order
        for preset_name in active_presets:
            if preset_name not in module.presets:
                raise ValueError(f"Preset '{preset_name}' not found in module")

            preset = module.presets[preset_name]

            # First, load preset's includes
            for include_path in preset.includes:
                included = self._load_include(include_path)
                merged_vars.update(included.vars)
                merged_tasks.update(included.tasks)
                merged_modules.update(included.modules)

            # Then apply preset's own content (override includes)
            merged_vars.update(preset.vars)
            merged_tasks.update(preset.tasks)
            merged_modules.update(preset.modules)

        # 4. Module's own vars/tasks/modules have highest priority
        merged_vars.update(module.vars)
        merged_tasks.update(module.tasks)
        merged_modules.update(module.modules)

        # Create new module with merged content
        return Module(
            name=module.name,
            vars=merged_vars,
            tasks=merged_tasks,
            modules=merged_modules,
            includes=[],  # Already processed
            presets={},  # Already processed
            defaults=[],  # Already processed
        )

    def _load_include(self, include_path: str) -> Module:
        """Load an include file and return its parsed module.

        Args:
            include_path: Path to the include file (relative to base_dir).

        Returns:
            Parsed Module from the include file.
        """
        from qwl.ast.parser import Parser

        # Resolve the path
        resolved_path = self.resolver._resolve_module_source(
            include_path, self.base_dir
        )

        # Parse the file
        parser = Parser()
        included = parser.parse_file(str(resolved_path))

        return included

    def _compile_with_bfs(
        self, root_module: Module, env_tree: Dict[str, Any], root_task_names: List[str]
    ) -> List[BashFunction]:
        """Compile tasks using BFS traversal from root tasks.

        This implements the Phase 2 algorithm:
        - Start from root tasks
        - BFS to discover dependencies
        - Canonical aliasing (dedup by env_hash)
        - Body-hash deduplication

        Args:
            root_module: The root module.
            env_tree: Full environment tree.
            root_task_names: Names of root tasks to start from.

        Returns:
            List of BashFunctions in dependency order.
        """
        # Queue: (alias, task_name) tuples
        # Empty alias means root module
        queue: deque[Tuple[str, str]] = deque()

        # Track visited (canonical FQN -> True)
        visited: Set[str] = set()

        # Track body hashes for deduplication
        body_hash_to_fqn: Dict[str, str] = {}

        # Result: list of (fqn, BashFunction)
        compiled: List[Tuple[str, BashFunction]] = []

        # Seed queue with root tasks
        for task_name in root_task_names:
            queue.append(("", task_name))

        while queue:
            alias, task_name = queue.popleft()

            # Get canonical FQN
            canonical_fqn = self.resolver.get_canonical_fqn(alias, task_name)

            if canonical_fqn in visited:
                continue
            visited.add(canonical_fqn)

            # Get the module and task
            if alias == "":
                mod = root_module
                mod_env = env_tree
            else:
                mod = self.resolver._module_cache.get(alias)
                if mod is None:
                    continue
                mod_env = env_tree.get(alias, {})

            task = mod.tasks.get(task_name)
            if task is None:
                continue

            # Detect dependencies before rendering (AST-based)
            if task.uses:
                deps = self._detect_deps_from_uses(task.uses, task.with_, mod_env)
            else:
                deps = self._detect_deps_from_template(task.run or "", mod_env)

            # Add dependencies to queue
            for dep_alias, dep_task in deps:
                dep_fqn = self.resolver.get_canonical_fqn(dep_alias, dep_task)
                if dep_fqn not in visited:
                    queue.append((dep_alias, dep_task))

            # Compile the task
            fn = self._compile_task(alias, task, mod_env)

            # Also check for dependencies in the rendered body (post-render)
            # These are canonical names like "log:_should_log" that weren't
            # detected from the template but appear after rendering
            for dep_canonical in fn.dependencies:
                if dep_canonical not in visited and ":" in dep_canonical:
                    dep_alias, dep_task = dep_canonical.split(":", 1)
                    queue.append((dep_alias, dep_task))

            # Body-hash deduplication
            body_hash = hashlib.sha256(fn.body.encode()).hexdigest()[:16]
            if body_hash in body_hash_to_fqn:
                # Skip duplicate body - just record the alias
                continue
            body_hash_to_fqn[body_hash] = canonical_fqn

            compiled.append((canonical_fqn, fn))

        # Return functions in order (dependencies first due to BFS)
        # Actually, BFS gives us forward order, but bash doesn't care about order
        # since functions can be defined after they're referenced
        return [fn for _, fn in compiled]

    def _compile_task(
        self, module_name: str, task: Task, env_tree: Dict[str, Any]
    ) -> BashFunction:
        """Compile a single Task to a BashFunction.

        Args:
            module_name: The parent module's name (for namespacing). Empty string for root.
            task: The Task to compile.
            env_tree: Full environment tree from resolver.

        Returns:
            BashFunction with rendered body and dependencies detected.
        """
        # Root tasks have no prefix, imported tasks have module:task format
        fn_name = task.name if module_name == "" else f"{module_name}:{task.name}"

        # Build task-local context: flattened env + resolved task vars
        task_context = dict(env_tree)
        if task.vars:
            # Resolve vars - vars can reference other vars or env values
            resolved_vars = self._resolve_vars(task.vars, task_context)
            task_context.update(resolved_vars)

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
                raise ValueError(
                    f"Invalid uses reference: {uses} (expected module.task)"
                )

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

    def _resolve_vars(
        self, vars_dict: Dict[str, Any], base_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Resolve vars by rendering any {{ }} references in their values.

        Vars can reference other vars or values from the base context.
        We process vars in order, adding each resolved var to the context
        so later vars can reference earlier ones.

        Args:
            vars_dict: Dictionary of variable names to values (may contain {{ }}).
            base_context: The base context (env_tree) to start with.

        Returns:
            Dictionary of resolved variable values.
        """
        from jinja2 import Environment

        resolved: Dict[str, Any] = {}
        # Build up context incrementally so vars can reference earlier vars
        current_context = dict(base_context)

        env = Environment()

        for var_name, var_value in vars_dict.items():
            if isinstance(var_value, str) and "{{" in var_value:
                # Render the var value through Jinja
                tmpl = env.from_string(var_value)
                resolved_value = tmpl.render(**current_context)
                resolved[var_name] = resolved_value
            else:
                # Non-string or no template syntax, use as-is
                resolved[var_name] = var_value

            # Add to current context for subsequent vars
            current_context[var_name] = resolved[var_name]

        return resolved

    def _render(self, template: str, context: Dict[str, Any]) -> str:
        """Render a Jinja template string with context.

        Handles special {% qx %}...{% xq %} blocks for remote execution boundaries.
        These blocks generate heredocs with escaped $ and included dependencies.

        Args:
            template: Jinja template string.
            context: Variables to render with.

        Returns:
            Rendered string.
        """
        from jinja2 import Environment

        # First, process {% qx %}...{% xq %} blocks
        template = self._process_qx_blocks(template, context)

        env = Environment()
        tmpl = env.from_string(template)
        return tmpl.render(**context)

    def _process_qx_blocks(self, template: str, context: Dict[str, Any]) -> str:
        """Process {% qx %}...{% xq %} remote execution boundary blocks.

        These blocks define code that should be executed on a remote shell.
        The compiler will:
        1. Detect task references inside the block
        2. Generate a unique heredoc delimiter
        3. Include dependencies via module:include
        4. Escape $ as \\$ for remote evaluation

        Args:
            template: Template string that may contain {% qx %} blocks.
            context: Environment context for resolving task references.

        Returns:
            Template with {% qx %} blocks replaced by heredoc constructs.
        """
        # Pattern to match {% qx %}...{% xq %} blocks
        pattern = r"\{%\s*qx\s*%\}(.*?)\{%\s*xq\s*%\}"

        def replace_qx_block(match: re.Match) -> str:
            block_content = match.group(1)
            return self._generate_heredoc_block(block_content, context)

        return re.sub(pattern, replace_qx_block, template, flags=re.DOTALL)

    def _generate_heredoc_block(
        self, block_content: str, context: Dict[str, Any]
    ) -> str:
        """Generate a heredoc block for remote execution.

        Args:
            block_content: The content inside {% qx %}...{% xq %}.
            context: Environment context.

        Returns:
            Heredoc construct with dependencies included.
        """
        import uuid

        # Generate unique heredoc delimiter
        heredoc_id = f"QWEX_{uuid.uuid4().hex[:8].upper()}"

        # Detect task references in the block ({{ module.task }} patterns)
        # These will be rendered to canonical names like module:task
        task_refs = self._detect_task_refs_in_block(block_content, context)

        # Escape $ in the block content for remote evaluation
        # But preserve {{ }} which will be rendered by Jinja later
        escaped_content = self._escape_for_heredoc(block_content)

        # Build the heredoc
        if task_refs:
            deps_list = " ".join(sorted(task_refs))
            heredoc = f"""<< '{heredoc_id}'
$(module:include {deps_list})
{escaped_content}
{heredoc_id}"""
        else:
            heredoc = f"""<< '{heredoc_id}'
{escaped_content}
{heredoc_id}"""

        return heredoc

    def _detect_task_refs_in_block(
        self, block: str, context: Dict[str, Any]
    ) -> Set[str]:
        """Detect task references in a {% qx %} block.

        Looks for {{ module.task }} patterns and resolves them to canonical names.

        Args:
            block: Content of the qx block.
            context: Environment context.

        Returns:
            Set of canonical task names (e.g., {'log:debug', 'utils:color'}).
        """
        refs: Set[str] = set()

        # Pattern: {{ module.task }} - module reference
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)"
        matches = re.findall(pattern, block)

        for module_ref, task_ref in matches:
            if module_ref in context and isinstance(context[module_ref], dict):
                module_env = context[module_ref]
                if task_ref in module_env and isinstance(module_env[task_ref], str):
                    canonical = module_env[task_ref]
                    refs.add(canonical)

        # Also detect already-canonical references (module:task patterns)
        canonical_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*)\b"
        canonical_matches = re.findall(canonical_pattern, block)
        refs.update(canonical_matches)

        return refs

    def _escape_for_heredoc(self, content: str) -> str:
        """Escape content for use in a heredoc.

        Escapes $ as \\$ so variables are evaluated on the remote shell,
        not the local shell.

        Args:
            content: Content to escape.

        Returns:
            Escaped content.
        """
        # Escape $ but not {{ }} (Jinja will process those)
        # Also don't escape $( ) for command substitution - those get escaped too
        # The heredoc is quoted (<<'EOF') so we need to escape $ for later evaluation
        return content.replace("$", "\\$")

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

    def _detect_deps_from_template(
        self, template: str, env_tree: Dict[str, Any]
    ) -> Set[Tuple[str, str]]:
        """Detect dependencies from Jinja template before rendering (AST-based).

        Looks for patterns like {{ module.task }} in the template and resolves
        them to (alias, task_name) tuples.

        Args:
            template: Jinja template string (unrendered).
            env_tree: Environment tree for resolving module references.

        Returns:
            Set of (alias, task_name) tuples for dependencies.
        """
        deps: Set[Tuple[str, str]] = set()

        # Pattern: {{ module.task }} or {{ module.task ... }}
        # Also matches {{ module.task | filter }} etc.
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)"
        matches = re.findall(pattern, template)

        for module_ref, task_ref in matches:
            # Check if module_ref is actually a module in env_tree
            if module_ref in env_tree and isinstance(env_tree[module_ref], dict):
                # It's a module reference
                module_env = env_tree[module_ref]
                # Check if task_ref is a task in that module
                if task_ref in module_env and isinstance(module_env[task_ref], str):
                    # Verify it's a canonical task name (contains : or is simple name)
                    canonical = module_env[task_ref]
                    if ":" in canonical:
                        alias, task_name = canonical.split(":", 1)
                        deps.add((alias, task_name))
                    else:
                        # Root task - alias is empty
                        deps.add(("", task_ref))

        return deps

    def _detect_deps_from_uses(
        self, uses: str, with_items: List[Any], env_tree: Dict[str, Any]
    ) -> Set[Tuple[str, str]]:
        """Detect dependencies from uses/with block.

        Args:
            uses: Reference to task (e.g., "steps.compose").
            with_items: List of items (may contain nested run templates).
            env_tree: Environment tree.

        Returns:
            Set of (alias, task_name) tuples.
        """
        deps: Set[Tuple[str, str]] = set()

        # Parse the uses reference
        parts = uses.split(".")
        if len(parts) == 2:
            module_ref, task_ref = parts
            if module_ref in env_tree and isinstance(env_tree[module_ref], dict):
                module_env = env_tree[module_ref]
                if task_ref in module_env:
                    canonical = module_env[task_ref]
                    if ":" in canonical:
                        alias, task_name = canonical.split(":", 1)
                        deps.add((alias, task_name))

        # Also scan with_items for nested run templates
        for item in with_items:
            if isinstance(item, dict):
                run_cmd = item.get("run")
                if run_cmd and isinstance(run_cmd, str):
                    nested_deps = self._detect_deps_from_template(run_cmd, env_tree)
                    deps.update(nested_deps)

        return deps

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
