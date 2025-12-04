"""Tests for qwml engine."""

from qwml import template, inline, compile_layers, compile_stack


def noop():
    """Helper to create noop layer."""
    return template("noop.sh.j2", name="noop")


def agent(**props):
    """Helper to create agent layer."""
    return template("agent.sh.j2", props=props, name="agent")


def test_noop_template_renders():
    """Noop template should just exec "$@"."""
    layer = noop()
    output = layer.render({})
    assert 'exec "$@"' in output


def test_single_noop_compiles():
    """Single noop should compile to minimal script."""
    script = compile_layers([noop()], {})
    assert "#!/bin/sh" in script
    assert 'exec "$@"' in script


def test_all_noops_stack():
    """Stack of all noops should compile."""
    script = compile_stack(
        access=noop(),
        allocation=noop(),
        arena=noop(),
        agent=noop(),
    )
    assert "#!/bin/sh" in script
    assert "_layer_0" in script


def test_inline_layer_preserves_script():
    """Inline layer should preserve custom script."""
    custom = 'echo "hello"\nexec "$@"'
    layer = inline(custom, name="custom")
    assert layer.render({}) == custom


def test_agent_template_has_logging():
    """Agent template should include logging and status reporting."""
    layer = agent(qwex_home="~/.qwex", run_id="test-123")
    rendered = layer.render({})
    assert "mkdir -p" in rendered
    assert "statuses.jsonl" in rendered
    assert "EXIT_CODE" in rendered


def test_template_with_props():
    """Template should receive props."""
    layer = template("ssh.sh.j2", props={"host": "example.com", "user": "admin"})
    rendered = layer.render({})
    assert "admin@example.com" in rendered


def test_mixed_layers_compile():
    """Mix of template and inline layers should compile correctly."""
    script = compile_stack(
        access=noop(),
        allocation=inline('echo "allocating"\nexec "$@"', name="alloc"),
        arena=noop(),
        agent=agent(run_id="test-123"),
    )
    assert "#!/bin/sh" in script
    assert "allocating" in script
    assert "statuses.jsonl" in script


def test_layer_chaining():
    """Layers should chain via function calls."""
    script = compile_layers(
        [
            inline('echo "L1"\nexec "$@"', name="L1"),
            inline('echo "L2"\nexec "$@"', name="L2"),
        ],
        {},
    )
    assert "_layer_0" in script
    assert "_layer_1" in script
    assert '"L1"' in script
    assert '"L2"' in script


def test_inline_template_with_jinja():
    """Inline template content should support Jinja interpolation."""
    layer = template(
        content='ssh {{ user }}@{{ host }} "$@"',
        props={"user": "admin", "host": "server.com"},
        name="ssh-inline",
    )
    rendered = layer.render({})
    assert "admin@server.com" in rendered


def test_template_requires_path_or_content():
    """Template must have either path or content."""
    import pytest

    with pytest.raises(ValueError, match="Must provide either"):
        template()  # Neither path nor content


def test_template_not_both_path_and_content():
    """Template cannot have both path and content."""
    import pytest

    with pytest.raises(ValueError, match="Cannot provide both"):
        template("noop.sh.j2", content='exec "$@"')


if __name__ == "__main__":
    test_noop_template_renders()
    test_single_noop_compiles()
    test_all_noops_stack()
    test_inline_layer_preserves_script()
    test_agent_template_has_logging()
    test_template_with_props()
    test_mixed_layers_compile()
    test_layer_chaining()
    test_inline_template_with_jinja()
    # Skip pytest-dependent tests in direct run
    print("All tests passed!")
