"""Tests for component system."""

import pytest
from qwexcli.lib.component import (
    Component,
    Script,
    Step,
    VarSpec,
    parse_component_ref,
    load_component_from_string,
)


def test_parse_component_ref_with_function():
    """Test parsing component reference with function name."""
    path, func = parse_component_ref("executors/ssh:exec")
    assert path == "executors/ssh"
    assert func == "exec"


def test_parse_component_ref_without_function():
    """Test parsing component reference without function name."""
    path, func = parse_component_ref("executors/ssh")
    assert path == "executors/ssh"
    assert func is None


def test_component_with_tags():
    """Test that component can have tags instead of kind."""
    yaml_str = """
name: test
tags: [executor, inline]
description: Test component
vars:
  HOST:
    required: true
scripts:
  exec: echo "hello"
"""
    comp = load_component_from_string(yaml_str)
    assert comp.name == "test"
    assert comp.tags == ["executor", "inline"]
    assert "HOST" in comp.vars


def test_component_with_empty_tags():
    """Test that component can have empty tags."""
    yaml_str = """
name: test
description: Test component
scripts:
  exec: echo "hello"
"""
    comp = load_component_from_string(yaml_str)
    assert comp.name == "test"
    assert comp.tags == []


def test_script_with_run():
    """Test script with simple run command."""
    script = Script(run="echo hello")
    assert script.run == "echo hello"
    assert script.steps is None


def test_script_with_steps():
    """Test script with steps structure."""
    yaml_str = """
name: test
tags: [workflow]
scripts:
  main:
    steps:
      - name: Setup
        run: echo "setup"
      - name: Build
        run: echo "build"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["main"]
    assert script.run is None
    assert script.steps is not None
    assert len(script.steps) == 2
    assert script.steps[0].name == "Setup"
    assert script.steps[0].run == 'echo "setup"'
    assert script.steps[1].name == "Build"


def test_script_cannot_have_both_run_and_steps():
    """Test that script cannot have both run and steps."""
    with pytest.raises(ValueError, match="cannot have both"):
        Script(run="echo hi", steps=[Step(run="echo bye")])


def test_script_must_have_run_or_steps():
    """Test that script must have either run or steps."""
    with pytest.raises(ValueError, match="must have either"):
        Script()


def test_step_with_run():
    """Test step with run command."""
    step = Step(name="Test", run="echo hi")
    assert step.name == "Test"
    assert step.run == "echo hi"
    assert step.uses is None


def test_step_with_uses():
    """Test step with uses (component reference)."""
    step = Step(name="Push", uses="storages/git_direct:push", with_={"REMOTE_URL": "ssh://..."})
    assert step.name == "Push"
    assert step.uses == "storages/git_direct:push"
    assert step.with_ == {"REMOTE_URL": "ssh://..."}
    assert step.run is None


def test_step_must_have_run_or_uses():
    """Test that step must have either run or uses."""
    with pytest.raises(ValueError, match="must have either"):
        Step(name="Invalid")


def test_component_normalizes_vars():
    """Test that component normalizes var specifications."""
    yaml_str = """
name: test
tags: [test]
vars:
  SIMPLE: "default_value"
  REQUIRED:
    required: true
  WITH_FLAG:
    flag: "host"
    default: "localhost"
scripts:
  exec: echo "test"
"""
    comp = load_component_from_string(yaml_str)
    
    # Check that all vars are normalized to VarSpec
    assert isinstance(comp.vars["SIMPLE"], VarSpec)
    assert comp.vars["SIMPLE"].default == "default_value"
    assert comp.vars["SIMPLE"].required is False
    
    assert isinstance(comp.vars["REQUIRED"], VarSpec)
    assert comp.vars["REQUIRED"].required is True
    
    assert isinstance(comp.vars["WITH_FLAG"], VarSpec)
    assert comp.vars["WITH_FLAG"].flag == "host"
    assert comp.vars["WITH_FLAG"].default == "localhost"


def test_component_normalizes_scripts():
    """Test that component normalizes script specifications."""
    yaml_str = """
name: test
tags: [test]
scripts:
  simple: echo "simple"
  complex:
    run: echo "complex"
    description: "A complex script"
  workflow:
    steps:
      - run: echo "step1"
      - run: echo "step2"
"""
    comp = load_component_from_string(yaml_str)
    
    # Check that all scripts are normalized to Script
    assert isinstance(comp.scripts["simple"], Script)
    assert comp.scripts["simple"].run == 'echo "simple"'
    
    assert isinstance(comp.scripts["complex"], Script)
    assert comp.scripts["complex"].run == 'echo "complex"'
    assert comp.scripts["complex"].description == "A complex script"
    
    assert isinstance(comp.scripts["workflow"], Script)
    assert comp.scripts["workflow"].steps is not None
    assert len(comp.scripts["workflow"].steps) == 2


def test_script_with_uses_in_steps():
    """Test script with steps that use other components."""
    yaml_str = """
name: pipeline
tags: [workflow]
scripts:
  deploy:
    steps:
      - name: Push code
        uses: storages/git_direct:push
        with:
          REMOTE_URL: "ssh://server/repo.git"
      - name: Execute
        uses: executors/ssh:exec
        with:
          HOST: "server"
          command: "deploy.sh"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["deploy"]
    
    assert len(script.steps) == 2
    
    # First step uses storage component
    assert script.steps[0].name == "Push code"
    assert script.steps[0].uses == "storages/git_direct:push"
    assert script.steps[0].with_["REMOTE_URL"] == "ssh://server/repo.git"
    
    # Second step uses executor component
    assert script.steps[1].name == "Execute"
    assert script.steps[1].uses == "executors/ssh:exec"
    assert script.steps[1].with_["HOST"] == "server"


def test_step_with_alias_field():
    """Test that 'with' field works as alias for 'with_'."""
    yaml_str = """
name: test
tags: [test]
scripts:
  main:
    steps:
      - name: Test
        uses: some/component:func
        with:
          KEY: value
"""
    comp = load_component_from_string(yaml_str)
    step = comp.scripts["main"].steps[0]
    assert step.with_ == {"KEY": "value"}
