"""Tests for the compiler module."""

from qwl.ast.spec import Module, Task
from qwl.compiler import Compiler, Renderer


def test_compile_simple_module():
    """Test compiling a simple module to BashScript IR."""
    module = Module(
        name="test",
        vars={"message": "hello"},
        tasks={
            "greet": Task(
                name="greet",
                run='echo "{{ vars.message }}"',
            )
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    assert len(script.functions) == 2  # task + help
    fn = script.functions[0]
    assert fn.name == "test:greet"
    assert 'echo "hello"' in fn.body

    help_fn = script.functions[1]
    assert help_fn.name == "help"
    assert "greet" in help_fn.body


def test_render_simple_script():
    """Test rendering BashScript IR to bash text."""
    module = Module(
        name="test",
        vars={},
        tasks={
            "hello": Task(
                name="hello",
                run="echo hello",
            )
        },
    )

    compiler = Compiler()
    renderer = Renderer()

    script = compiler.compile(module)
    bash = renderer.render(script)

    assert "#!/usr/bin/env bash" in bash
    assert "module:register_dependency ()" in bash
    assert "test:hello () {" in bash
    assert "echo hello" in bash
    assert 'module:register_dependency "test:hello"' in bash
    assert 'module:register_dependency "help"' in bash
    assert "help" in bash
