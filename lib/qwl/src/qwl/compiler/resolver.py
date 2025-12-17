"""Resolver - loads modules lazily and builds flat hash-indexed environment maps.

Phase 2 Implementation:
- Lazy module loading (only loads modules when referenced by reachable tasks)
- Flat hash-indexed maps instead of nested tree structure
- Support for canonical alias resolution (env_hash -> first alias seen in BFS)
"""

from pathlib import Path
from typing import Any, Dict, Optional
import hashlib
import json

from qwl.ast.parser import Parser
from qwl.ast.spec import Module


def _hash_source(path: Path) -> str:
    """Compute SHA256 hash of a source file."""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def _hash_env(source_hash: str, vars_dict: Dict[str, Any]) -> str:
    """Compute hash of (source_hash, resolved vars).
    
    This identifies a unique module instantiation (same source + same var bindings).
    """
    # Serialize vars deterministically
    vars_json = json.dumps(vars_dict, sort_keys=True, default=str)
    combined = f"{source_hash}:{vars_json}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


class Resolver:
    """Resolves module references using flat hash-indexed maps.
    
    Phase 2 Data Structures:
    - alias_to_source_hash: alias -> source file hash
    - source_hash_to_ast: source hash -> parsed Module AST
    - alias_to_env_hash: alias -> environment hash (source + vars)
    - env_hash_to_canonical_alias: env_hash -> first alias (BFS order)
    - env_hash_to_env: env_hash -> resolved environment dict
    - source_hash_to_path: source hash -> source file path
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize resolver with optional base directory for relative imports.

        Args:
            base_dir: Base directory for resolving relative module paths.
        """
        self.base_dir = base_dir or Path.cwd()
        self.parser = Parser()
        
        # Legacy compatibility: keep _module_cache for compiler access
        self._module_cache: Dict[str, Module] = {}
        self._source_map: Dict[str, Path] = {}
        
        # Phase 2 flat hash-indexed maps
        self.alias_to_source_hash: Dict[str, str] = {}
        self.source_hash_to_ast: Dict[str, Module] = {}
        self.alias_to_env_hash: Dict[str, str] = {}
        self.env_hash_to_canonical_alias: Dict[str, str] = {}
        self.env_hash_to_env: Dict[str, Dict[str, Any]] = {}
        self.source_hash_to_path: Dict[str, Path] = {}

    def resolve(self, root_module: Module) -> Dict[str, Any]:
        """Resolve all modules and build environment tree.
        
        This method now builds flat hash-indexed maps internally,
        but returns a nested env tree for backward compatibility with Phase 1 compiler.

        Args:
            root_module: The root module to start from.

        Returns:
            Environment dict with structure compatible with Phase 1 compiler.
        """
        # Clear previous state
        self._clear_state()
        
        # Register root module with special alias ""
        self._register_root_module(root_module)
        
        # Load all imported modules recursively (eager for now, will be lazy in compiler)
        self._load_modules_recursive(root_module, module_dir=self.base_dir)
        
        # Build flat hash-indexed maps
        self._build_flat_maps(root_module, alias="", parent_vars={})

        # Build and return nested env tree for backward compatibility
        env = self._build_env_tree(root_module)
        return env
    
    def _clear_state(self):
        """Clear all internal state for fresh resolution."""
        self._module_cache.clear()
        self._source_map.clear()
        self.alias_to_source_hash.clear()
        self.source_hash_to_ast.clear()
        self.alias_to_env_hash.clear()
        self.env_hash_to_canonical_alias.clear()
        self.env_hash_to_env.clear()
        self.source_hash_to_path.clear()
    
    def _register_root_module(self, root_module: Module) -> str:
        """Register the root module with a synthetic source hash."""
        # Root module doesn't have a file path, use a synthetic hash
        root_hash = hashlib.sha256(root_module.name.encode()).hexdigest()[:16]
        self.alias_to_source_hash[""] = root_hash
        self.source_hash_to_ast[root_hash] = root_module
        return root_hash
    
    def _build_flat_maps(
        self, 
        module: Module, 
        alias: str,
        parent_vars: Dict[str, Any],
        visited: Optional[set] = None
    ):
        """Build flat hash-indexed maps from module tree.
        
        Args:
            module: Current module to process.
            alias: The alias for this module (e.g., "", "log", "utils").
            parent_vars: Vars inherited from parent scope.
            visited: Set of already-visited aliases to prevent cycles.
        """
        if visited is None:
            visited = set()
        
        if alias in visited:
            return
        visited.add(alias)
        
        # Get source hash
        source_hash = self.alias_to_source_hash.get(alias)
        if source_hash is None:
            # This shouldn't happen if _load_modules_recursive was called
            return
        
        # Compute resolved vars (parent vars + module vars)
        resolved_vars = dict(parent_vars)
        resolved_vars.update(module.vars)
        
        # Compute env hash
        env_hash = _hash_env(source_hash, resolved_vars)
        self.alias_to_env_hash[alias] = env_hash
        
        # Register canonical alias (first one wins in BFS order)
        if env_hash not in self.env_hash_to_canonical_alias:
            self.env_hash_to_canonical_alias[env_hash] = alias
        
        # Build and store resolved environment
        env = self._build_module_env(module, alias, resolved_vars)
        self.env_hash_to_env[env_hash] = env
        
        # Process imported modules
        for mod_ref_name in module.modules:
            loaded = self._module_cache.get(mod_ref_name)
            if loaded:
                self._build_flat_maps(loaded, mod_ref_name, resolved_vars, visited)
    
    def _build_module_env(
        self, 
        module: Module, 
        alias: str, 
        resolved_vars: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build the environment dict for a single module.
        
        Args:
            module: The module to build env for.
            alias: The module's alias (empty string for root).
            resolved_vars: The fully resolved vars dict.
            
        Returns:
            Environment dict with vars and task mappings.
        """
        env: Dict[str, Any] = dict(resolved_vars)
        env["module_name"] = module.name
        
        # Add task name mappings
        is_root = alias == ""
        for task_name in module.tasks:
            if is_root:
                env[task_name] = task_name
            else:
                env[task_name] = f"{alias}:{task_name}"
        
        return env
    
    def get_canonical_alias(self, alias: str) -> str:
        """Get the canonical alias for a given alias.
        
        Two aliases are equivalent if they have the same env_hash
        (same source + same resolved vars).
        
        Args:
            alias: The alias to canonicalize.
            
        Returns:
            The canonical alias (first one seen in BFS order).
        """
        env_hash = self.alias_to_env_hash.get(alias)
        if env_hash is None:
            return alias
        return self.env_hash_to_canonical_alias.get(env_hash, alias)
    
    def get_canonical_fqn(self, alias: str, task_name: str) -> str:
        """Get the canonical fully-qualified name for a task.
        
        Args:
            alias: The module alias.
            task_name: The task name.
            
        Returns:
            Canonical FQN like "canonical_alias:task" or just "task" for root.
        """
        canonical_alias = self.get_canonical_alias(alias)
        if canonical_alias == "":
            return task_name
        return f"{canonical_alias}:{task_name}"

    def _load_modules_recursive(
        self,
        module: Module,
        visited: Optional[set] = None,
        module_dir: Optional[Path] = None,
    ):
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
                raise FileNotFoundError(
                    f"Module source not found: {mod_ref.source} (resolved to {source_path})"
                )

            loaded = self.parser.parse_file(str(source_path))
            self._module_cache[mod_ref.name] = loaded
            self._source_map[mod_ref.name] = source_path
            
            # Register in Phase 2 hash maps
            source_hash = _hash_source(source_path)
            self.alias_to_source_hash[mod_ref.name] = source_hash
            self.source_hash_to_ast[source_hash] = loaded
            self.source_hash_to_path[source_hash] = source_path

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

    def _build_env_tree(self, root_module: Module, is_root: bool = True) -> Dict[str, Any]:
        """Build the environment tree for Jinja rendering.

        Returns a flattened dictionary where:
        - vars are at the root
        - tasks are at the root (name -> canonical name)
        - imported modules are at the root (name -> env dict)
        
        Args:
            root_module: The module to build env for.
            is_root: If True, tasks use empty namespace (just "taskname").
        """
        # Start with vars
        env: Dict[str, Any] = dict(root_module.vars)

        # Add metadata
        env["module_name"] = root_module.name

        # Add tasks (name -> canonical name)
        # Root tasks have no prefix, imported tasks have module:task format
        for name in root_module.tasks:
            if is_root:
                env[name] = name  # Root: just "greet"
            else:
                env[name] = f"{root_module.name}:{name}"  # Imported: "log:debug"

        # Add imported modules to environment
        for mod_ref in root_module.modules.values():
            loaded = self._module_cache.get(mod_ref.name)
            if loaded:
                env[mod_ref.name] = self._build_env_tree(loaded, is_root=False)

        return env
