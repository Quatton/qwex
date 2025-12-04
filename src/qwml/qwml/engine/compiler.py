"""Compiler - takes layers and produces a single shell script.

Like ReactDOM.render() - takes a tree of components and produces output.
"""

from __future__ import annotations

from typing import Any, Sequence

from qwml.engine.layer import Layer


def compile_layers(layers: Sequence[Layer], ctx: dict[str, Any]) -> str:
    """Compile a list of layers into a single shell script.

    Layers are composed from outside-in:
    - layers[0] is the outermost (e.g., Access/L1)
    - layers[-1] is the innermost (e.g., Agent/L4)

    The compilation strategy:
    1. Each layer becomes a shell function
    2. Functions chain via "$@" (each layer calls the next)
    3. Entry point calls: _layer_0 _layer_1 ... _layer_n "$@"

    Args:
        layers: List of layers to compile
        ctx: Context dict passed to all layers

    Returns:
        Complete shell script
    """
    if not layers:
        return '#!/bin/sh\nset -euo pipefail\nexec "$@"'

    # Render each layer
    functions = []
    layer_names = []

    for i, layer in enumerate(layers):
        func_name = f"_layer_{i}"
        body = layer.render(ctx)
        layer_names.append(layer.name)

        # Indent the body for the function
        indented = "\n".join(
            f"  {line}" if line.strip() else "" for line in body.split("\n")
        )

        functions.append(f"""# Layer {i}: {layer.name}
{func_name}() {{
{indented}
}}""")

    # Build the call chain
    if len(layers) == 1:
        entry = '_layer_0 "$@"'
    else:
        chain = " ".join(f"_layer_{i}" for i in range(len(layers)))
        entry = f'{chain} "$@"'

    layers_comment = " -> ".join(layer_names)

    return f"""#!/bin/sh
# Compiled qwml script
# Layers: {layers_comment}
set -euo pipefail

{chr(10).join(functions)}

# Entry point
run() {{
  {entry}
}}

# Execute
run "$@"
"""


def compile_stack(
    access: Layer,
    allocation: Layer,
    arena: Layer,
    agent: Layer,
    ctx: dict[str, Any] | None = None,
) -> str:
    """Compile a 4-layer stack (the "4 A's") into a shell script.

    This is the canonical entry point - enforces the layer model.

    Args:
        access: L1 - connection layer (SSH, kubectl, localhost)
        allocation: L2 - resource provisioning (Slurm, K8s Job)
        arena: L3 - isolation (Docker, Singularity, Conda)
        agent: L4 - execution and artifact capture
        ctx: Context dict passed to all layers

    Returns:
        Complete shell script
    """
    ctx = ctx or {}
    return compile_layers([access, allocation, arena, agent], ctx)
