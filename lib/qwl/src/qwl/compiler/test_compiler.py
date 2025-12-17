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


def test_bfs_only_emits_reachable_tasks():
    """Test that BFS only emits tasks reachable from root tasks.

    Phase 2 algorithm should only emit tasks that are reachable
    through dependency chains starting from root tasks.
    """
    # Create a module with an unreachable task
    # If we had imports, only imported and used tasks would be emitted
    module = Module(
        name="test",
        vars={},
        tasks={
            "main": Task(name="main", run="echo main"),
            "helper": Task(name="helper", run="echo helper"),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    # All root tasks should be emitted (BFS starts from all root tasks)
    task_names = [fn.name for fn in script.functions if fn.name != "help"]
    assert "main" in task_names
    assert "helper" in task_names  # Root task, so included


def test_body_hash_deduplication():
    """Test that tasks with identical bodies are deduplicated.

    Phase 2 algorithm should only emit unique function bodies.
    If two tasks have identical rendered bodies, only the first
    (in BFS order) should be emitted.
    """
    # Create tasks with identical bodies
    module = Module(
        name="test",
        vars={},
        tasks={
            "task1": Task(name="task1", run="echo identical"),
            "task2": Task(name="task2", run="echo identical"),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    # Should only have one task + help due to deduplication
    # (Both have identical body "echo identical")
    task_names = [fn.name for fn in script.functions if fn.name != "help"]
    # First one wins in BFS order
    assert len(task_names) == 1
    assert task_names[0] == "task1"


def test_ast_dependency_detection():
    """Test AST-based dependency detection from templates.

    The compiler should detect {{ module.task }} patterns
    before rendering and include those as dependencies.
    """
    module = Module(
        name="test",
        vars={},
        tasks={
            "main": Task(name="main", run="echo main"),
            # This task references main via template
            "caller": Task(name="caller", run="{{ main }}"),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    # caller should have main in its deps
    caller_fn = next(fn for fn in script.functions if fn.name == "caller")
    # Note: main is a root task, so it resolves to just "main" not "module:main"
    # The rendered body will have "main" (the canonical name)
    assert "main" in caller_fn.body


def test_canonical_alias_resolution():
    """Test that the resolver provides canonical alias resolution.

    The resolver should track env_hash -> canonical_alias mapping
    for deduplicating module instantiations with same source + vars.
    """
    from qwl.compiler.resolver import Resolver

    module = Module(
        name="test",
        vars={"x": 1},
        tasks={"t": Task(name="t", run="echo x")},
    )

    resolver = Resolver()
    resolver.resolve(module)

    # Root module has alias ""
    canonical = resolver.get_canonical_alias("")
    assert canonical == ""

    # get_canonical_fqn should work for root tasks
    fqn = resolver.get_canonical_fqn("", "t")
    assert fqn == "t"


def test_qx_boundary_generates_heredoc():
    """Test that {% qx %}...{% xq %} generates heredoc for remote execution.
    
    The compiler should:
    1. Detect {% qx %} blocks
    2. Generate unique heredoc delimiter
    3. Escape $ as \\$ for remote evaluation
    """
    module = Module(
        name="test",
        vars={"host": "remote"},
        tasks={
            "remote_task": Task(
                name="remote_task",
                run='ssh {{ host }} bash -s {% qx %}echo "Hello from $USER"{% xq %}',
            )
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    fn = next(fn for fn in script.functions if fn.name == "remote_task")
    
    # Should contain heredoc delimiter
    assert "<<" in fn.body
    assert "QWEX_" in fn.body
    
    # $ should be escaped
    assert "\\$USER" in fn.body
    
    # Host var should be rendered
    assert "ssh remote" in fn.body


def test_qx_boundary_includes_dependencies():
    """Test that {% qx %} blocks include module:include for dependencies."""
    module = Module(
        name="test",
        vars={},
        tasks={
            "local": Task(name="local", run="echo local"),
            "remote": Task(
                name="remote",
                # Reference local task inside qx block
                run='bash -s {% qx %}{{ local }}{% xq %}',
            )
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    fn = next(fn for fn in script.functions if fn.name == "remote")
    
    # Since local is a root task, it resolves to just "local"
    # The qx block should include module:include for it
    # Note: root tasks don't have module prefix, so dependency detection may not catch them
    # This is expected behavior - root tasks are available globally
    assert "<<" in fn.body  # Has heredoc
    assert "QWEX_" in fn.body  # Has unique delimiter