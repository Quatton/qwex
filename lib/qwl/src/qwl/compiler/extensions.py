"""Jinja2 extensions for QWL template rendering."""

import random
import string
import os
from typing import Set, Dict, Any

from jinja2 import nodes
from jinja2.ext import Extension


class QxExtension(Extension):
    """Extension for {% qx %}...{% endqx %} remote execution boundary blocks.
    
    This extension marks code that should be executed on a remote shell.
    It handles:
    1. Detecting task references inside the block
    2. Including dependencies via module:include
    
    Unlike the previous regex-based approach, this does NOT generate heredocs.
    Users should write heredocs explicitly with their own delimiters.
    
    Example:
        vars:
          EOF: "{{ random(8) | upper }}"
        
        tasks:
          deploy:
            run: |
              ssh host bash -s <<'{{ EOF }}'
              {% qx %}
              {{ log.info }} "Running on remote"
              some_helper_function
              {% endqx %}
              {{ EOF }}
    """
    
    tags = {'qx'}
    
    def __init__(self, environment):
        super().__init__(environment)
        # Store context for dependency detection (set by compiler)
        # These are runtime attributes, not part of Environment's type definition
        environment.qx_context = {}  # type: ignore[attr-defined]
        environment.qx_dependencies = set()  # type: ignore[attr-defined]
    
    def parse(self, parser):
        """Parse the {% qx %}...{% endqx %} block."""
        lineno = next(parser.stream).lineno
        
        # Parse the body until we hit {% endqx %}
        body = parser.parse_statements(('name:endqx',), drop_needle=True)
        
        # Return a CallBlock that will process the content
        return nodes.CallBlock(
            self.call_method('_process_qx_block', []),
            [], [], body
        ).set_lineno(lineno)
    
    def _process_qx_block(self, caller):
        """Process the content inside a {% qx %} block.
        
        This method is called at render time with the block content.
        It detects dependencies and includes them via module:include.
        
        Args:
            caller: Function that returns the rendered block content.
            
        Returns:
            The block content with dependency inclusion prepended.
        """
        content = caller()
        
        # Get context and detect dependencies
        context = self.environment.qx_context  # type: ignore[attr-defined]
        deps = self._detect_task_refs(content, context)
        
        # Store dependencies for the compiler to use
        self.environment.qx_dependencies.update(deps)  # type: ignore[attr-defined]
        
        # If there are dependencies, prepend module:include
        if deps:
            deps_list = " ".join(sorted(deps))
            return f"$(module:include {deps_list})\n{content}"
        
        return content
    
    def _detect_task_refs(self, content: str, context: Dict[str, Any]) -> Set[str]:
        """Detect task references in the block content.
        
        Looks for canonical task names (module:task patterns).
        
        Args:
            content: Rendered content of the qx block.
            context: Environment context.
            
        Returns:
            Set of canonical task names.
        """
        import re
        refs: Set[str] = set()
        
        # Detect canonical references (module:task patterns)
        canonical_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*)\b"
        matches = re.findall(canonical_pattern, content)
        refs.update(matches)
        
        return refs


def random_string(length: int = 8) -> str:
    """Generate a random alphanumeric string.
    
    Args:
        length: Length of the string to generate.
        
    Returns:
        Random string of specified length.
    """
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def env_var(name: str, default: str = "") -> str:
    """Get an environment variable value.
    
    Args:
        name: Name of the environment variable.
        default: Default value if not set.
        
    Returns:
        Environment variable value or default.
    """
    return os.environ.get(name, default)


def get_qwl_jinja_env():
    """Create a Jinja2 Environment with QWL extensions and filters.
    
    Returns:
        Configured Jinja2 Environment.
    """
    from jinja2 import Environment
    
    env = Environment(extensions=[QxExtension])
    
    # Add custom filters
    env.filters['random'] = lambda length=8: random_string(length)
    env.globals['random'] = random_string
    env.globals['env'] = env_var
    
    return env
