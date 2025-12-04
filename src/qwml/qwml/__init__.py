"""qwml - Qwex Markup Language

Composable shell layer compiler. "React for shell scripts."

Engine-only: templates define behavior, this just renders them.
"""

# Engine (core abstractions)
from qwml.engine import Layer, TemplateLayer, compile_layers, compile_stack
from qwml.engine.layer import inline, template

__all__ = [
    # Core classes
    "Layer",
    "TemplateLayer",
    # Factory functions
    "template",
    "inline",
    # Compiler
    "compile_stack",
    "compile_layers",
]
