"""Tests for the compiler module."""

from qwl.ast.spec import Module, Task
from qwl.compiler import Compiler, Renderer


def test_compile_simple_module():
    """Test compiling a simple module to BashScript IR.
    
    Root module tasks use empty namespace (just task name, no prefix).
    """
    module = Module(
        name="test",
        vars={"message": "hello"},
        tasks={
            "greet": Task(
                name="greet",
                run='echo "{{ message }}"',
            )
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    assert len(script.functions) == 2  # task + help
    fn = script.functions[0]
    # Root tasks have no namespace prefix
    assert fn.name == "greet"
    assert 'echo "hello"' in fn.body

    help_fn = script.functions[1]
    assert help_fn.name == "help"
    assert "greet" in help_fn.body


def test_render_simple_script():
    """Test rendering BashScript IR to bash text.
    
    Root module tasks are emitted without namespace prefix.
    """
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
    # Root tasks have no prefix
    assert "hello () {" in bash
    assert "echo hello" in bash
    assert 'module:register_dependency "hello"' in bash
    assert 'module:register_dependency "help"' in bash


def test_module_header_auto_injected():
    """Test that @module functions are automatically injected.
    
    The renderer should auto-inject module:register_dependency, 
    module:collect_dependencies, and module:include functions
    without requiring explicit import.
    """
    module = Module(
        name="test",
        vars={},
        tasks={
            "noop": Task(name="noop", run="echo noop"),
        },
    )

    compiler = Compiler()
    renderer = Renderer()
    script = compiler.compile(module)
    bash = renderer.render(script)

    # All @module functions should be present
    assert "module:register_dependency ()" in bash
    assert "module:collect_dependencies ()" in bash
    assert "module:include()" in bash
    
    # They should be callable (function definitions)
    assert "MODULE_DEPENDENCIES_HASHSET" in bash


def test_root_namespace_is_empty():
    """Test that root module tasks have empty namespace.
    
    Root tasks should be callable as just 'taskname' not 'module:taskname'.
    Imported module tasks should have their module prefix.
    """
    module = Module(
        name="mymodule",
        vars={},
        tasks={
            "task1": Task(name="task1", run="echo task1"),
            "task2": Task(name="task2", run="echo task2"),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    # Root tasks should have no prefix
    task_names = [fn.name for fn in script.functions if fn.name != "help"]
    assert "task1" in task_names
    assert "task2" in task_names
    # Should NOT have module prefix
    assert "mymodule:task1" not in task_names
    assert "mymodule:task2" not in task_names


def test_entrypoint_rendered():
    """Test that entrypoint is rendered at the end of script."""
    module = Module(
        name="test",
        vars={},
        tasks={"noop": Task(name="noop", run=":")},
    )

    compiler = Compiler()
    renderer = Renderer()
    script = compiler.compile(module)
    bash = renderer.render(script)

    # Entrypoint should be at the end
    assert bash.strip().endswith('if [ $# -eq 0 ]; then help; else "$@"; fi')
    assert "help" in bash
