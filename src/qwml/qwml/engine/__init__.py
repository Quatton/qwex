"""qwml.engine - Core template engine for composable shell layers.

This is like React's core - just the rendering engine, no components.
"""

from qwml.engine.layer import Layer, TemplateLayer
from qwml.engine.compiler import compile_layers, compile_stack

__all__ = ["Layer", "TemplateLayer", "compile_layers", "compile_stack"]
