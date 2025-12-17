"""Resolver - loads modules recursively and builds environment tree."""

from pathlib import Path
from typing import Any, Dict, Optional

from qwl.ast.parser import Parser
from qwl.ast.spec import Module


class Resolver:
    """Resolves module references and builds Jinja environment context."""

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize resolver with optional base directory for relative imports.

        Args:
            base_dir: Base directory for resolving relative module paths.
        """
        self.base_dir = base_dir or Path.cwd()
        self.parser = Parser()
        self._module_cache: Dict[str, Module] = {}

    def resolve(self, root_module: Module) -> Dict[str, Any]:
        """Resolve all modules and build environment tree.

        Args:
            root_module: The root module to start from.

        Returns:
            Environment dict with structure:
            {
              "name": str,
              "vars": dict,
              "tasks": dict (name -> canonical task name),
              "module_name": { ... recursively ... },
              ...
            }
        """
        # Load all imported modules recursively
        self._load_modules_recursive(root_module, module_dir=self.base_dir)

        # Build environment tree
        env = self._build_env_tree(root_module)

        return env

    def _load_modules_recursive(self, module: Module, visited: Optional[set] = None, module_dir: Optional[Path] = None):
        """Load all modules referenced by the given module (recursive).

        Args:
            module: Module to process.
            visited: Set of already-visited module names (to prevent infinite loops).
            module_dir: Directory where this module file is located (for relative imports).
        """
        if visited is None:
            visited = set()

        if module.name in visited:
            return
        visited.add(module.name)

        # If no module_dir provided, use base_dir
        if module_dir is None:
            module_dir = self.base_dir

        for mod_ref in module.modules.values():
            if mod_ref.name in self._module_cache:
                continue

            # Resolve source path relative to the module's own directory
            source_path = module_dir / mod_ref.source
            if not source_path.exists():
                raise FileNotFoundError(f"Module source not found: {mod_ref.source} (resolved to {source_path})")

            loaded = self.parser.parse_file(str(source_path))
            self._module_cache[mod_ref.name] = loaded

            # Recursively load modules from imported module, with its own directory as base
            module_source_dir = source_path.parent
            self._load_modules_recursive(loaded, visited, module_source_dir)

    def _resolve_path(self, source: str) -> Path:
        """Resolve a source path relative to base_dir.

        Args:
            source: Source path (relative or absolute).

        Returns:
            Resolved Path object.
        """
        p = Path(source)
        if p.is_absolute():
            return p

        resolved = self.base_dir / p
        if not resolved.exists():
            raise FileNotFoundError(f"Module source not found: {source}")

        return resolved

    def _build_env_tree(self, root_module: Module) -> Dict[str, Any]:
        """Build the environment tree for Jinja rendering.

        Args:
            root_module: Root module.

        Returns:
            Environment dict.
        """
        env: Dict[str, Any] = {
            "name": root_module.name,
            "vars": dict(root_module.vars),
            "tasks": {name: f"{root_module.name}:{name}" for name in root_module.tasks},
        }

        # Add imported modules to environment
        for mod_ref in root_module.modules.values():
            loaded = self._module_cache.get(mod_ref.name)
            if loaded:
                env[mod_ref.name] = self._build_env_tree(loaded)

        return env

    def get_args_context(self, task_args: list) -> Dict[str, str]:
        """Build args context for a task (renders args to bash variable references).

        Args:
            task_args: List of Arg objects.

        Returns:
            Dict mapping arg name to bash reference (e.g., "$1", "$2", "${X:-default}").
        """
        args_ctx: Dict[str, str] = {}

        for arg in task_args:
            if arg.positional > 0:
                # Positional arg: $1, $2, etc.
                args_ctx[arg.name] = f"${{{arg.positional}:-{arg.default or ''}}}"
            else:
                # Named arg: ${NAME:-default}
                args_ctx[arg.name] = f"${{{arg.name.upper()}:-{arg.default or ''}}}"

        return args_ctx
