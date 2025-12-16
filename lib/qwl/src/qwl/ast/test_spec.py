from qwl.ast.spec import Task
import pytest


def test_task_from_shorthand_string():
    t = Task.from_dict("echo", "echo hi")
    assert t.name == "echo"
    assert t.run == "echo hi"
    assert t.vars == {}
    assert t.env == {}


def test_task_from_mapping():
    raw = {
        "run": "echo {{ vars.message }}",
        "vars": {"a": 1},
        "env": {"FOO": "bar"},
    }
    t = Task.from_dict("echo", raw)
    assert t.name == "echo"
    assert t.run == "echo {{ vars.message }}"
    assert t.vars == {"a": 1}
    assert t.env == {"FOO": "bar"}


def test_task_invalid_type_raises():
    with pytest.raises(TypeError):
        Task.from_dict("bad", 123)


def test_task_vars_env_type_validation():
    with pytest.raises(TypeError):
        Task.from_dict("t", {"run": "echo", "vars": "not-a-dict"})

    with pytest.raises(TypeError):
        Task.from_dict("t", {"run": "echo", "env": "not-a-dict"})
