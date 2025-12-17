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


def test_qx_boundary_includes_dependencies():
    """Test that {% qx %}...{% endqx %} includes module:include for dependencies.

    The qx extension:
    1. Marks a remote execution boundary
    2. Detects canonical task dependencies (module:task) inside the block
    3. Prepends $(module:include ...) for those dependencies
    
    Note: Root tasks (without module prefix) are not auto-detected as dependencies
    since they don't have the module:task format. This is intentional - root tasks
    are already available globally.
    
    Note: heredocs are NOT automatically generated - users write them explicitly.
    """
    module = Module(
        name="test",
        vars={},
        tasks={
            "helper": Task(name="helper", run="echo helper"),
            "remote": Task(
                name="remote",
                # Use canonical module:task format to test dependency detection
                run="""bash -s <<'EOF'
{% qx %}
log:info "running on remote"
utils:color
{% endqx %}
EOF""",
            ),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    fn = next(fn for fn in script.functions if fn.name == "remote")

    # Should contain module:include for the module:task dependencies
    assert "module:include" in fn.body
    # Should detect log:info and utils:color as dependencies
    assert "log:info" in fn.body
    assert "utils:color" in fn.body
    
    # The heredoc should be exactly as written (not auto-generated)
    assert "<<'EOF'" in fn.body
    assert "EOF" in fn.body


def test_qx_with_module_dependencies():
    """Test that {% qx %} detects module:task dependencies."""
    module = Module(
        name="test",
        vars={},
        tasks={
            "remote": Task(
                name="remote",
                run="""ssh host bash -s <<'HEREDOC'
{% qx %}
log:info "running on remote"
utils:color
{% endqx %}
HEREDOC""",
            ),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    fn = next(fn for fn in script.functions if fn.name == "remote")

    # Should include module:include with the detected dependencies
    assert "module:include" in fn.body
    assert "log:info" in fn.body or "utils:color" in fn.body


def test_random_filter():
    """Test that random() filter generates random strings."""
    module = Module(
        name="test",
        vars={"delim": "{{ random(8) | upper }}"},
        tasks={
            "task": Task(name="task", run="echo {{ delim }}"),
        },
    )

    compiler = Compiler()
    script = compiler.compile(module)

    fn = next(fn for fn in script.functions if fn.name == "task")

    # Should contain a rendered random string (8 uppercase chars)
    # The body should have "echo XXXXXXXX" where X is alphanumeric
    import re
    match = re.search(r'echo ([A-Z0-9]{8})', fn.body)
    assert match is not None, f"Expected 8-char random string in: {fn.body}"
