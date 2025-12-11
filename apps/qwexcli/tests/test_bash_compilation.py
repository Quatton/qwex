"""Tests for bash script compilation from components."""

import pytest
from qwexcli.lib.component import load_component_from_string
from qwexcli.lib.template import interpolate


def test_compile_simple_script():
    """Test compiling a simple script with vars."""
    yaml_str = """
name: test
tags: [test]
vars:
  NAME: "World"
scripts:
  greet:
    run: |
      echo "Hello, ${{ vars.NAME }}!"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["greet"]
    
    context = {"vars": {"NAME": "Alice"}, "inputs": {}, "env": {}}
    compiled = interpolate(script.run, context)
    
    assert 'echo "Hello, Alice!"' in compiled


def test_compile_with_env_vars():
    """Test that env vars are available in context."""
    yaml_str = """
name: test
tags: [test]
scripts:
  show_path:
    run: |
      echo "PATH is $PATH"
      echo "Custom var: ${{ vars.CUSTOM }}"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["show_path"]
    
    import os
    context = {"vars": {"CUSTOM": "value"}, "inputs": {}, "env": dict(os.environ)}
    compiled = interpolate(script.run, context)
    
    # The $PATH should remain as-is (bash env var)
    assert "echo \"PATH is $PATH\"" in compiled
    # But ${{ vars.CUSTOM }} should be interpolated
    assert 'echo "Custom var: value"' in compiled


def test_compile_executor_script():
    """Test compiling the SSH executor script with inputs."""
    yaml_str = """
name: ssh
tags: [executor]
vars:
  REPO_CACHE: "$HOME/cache"
  RUN_DIR: "$HOME/runs"
scripts:
  exec:
    run: |
      #!/usr/bin/env bash
      set -euo pipefail
      
      GIT_HEAD="${{ inputs.git_head }}"
      RUN_ID="${{ inputs.run_id }}"
      CACHE="${{ vars.REPO_CACHE }}"
      
      echo "Running $RUN_ID at $GIT_HEAD"
      echo "Cache: $CACHE"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["exec"]
    
    context = {
        "vars": {"REPO_CACHE": "/home/user/cache", "RUN_DIR": "/home/user/runs"},
        "inputs": {"git_head": "abc123", "run_id": "test-20231201-1234"},
        "env": {}
    }
    compiled = interpolate(script.run, context)
    
    assert 'GIT_HEAD="abc123"' in compiled
    assert 'RUN_ID="test-20231201-1234"' in compiled
    assert 'CACHE="/home/user/cache"' in compiled


def test_compile_storage_script():
    """Test compiling the git_direct storage script."""
    yaml_str = """
name: git_direct
tags: [storage]
vars:
  REMOTE_NAME: "origin"
  REMOTE_URL:
    required: true
  PUSH_ON_RUN: "true"
scripts:
  push:
    run: |
      #!/usr/bin/env bash
      set -euo pipefail
      
      REMOTE_NAME="${{ vars.REMOTE_NAME }}"
      REMOTE_URL="${{ vars.REMOTE_URL }}"
      
      echo "Pushing to $REMOTE_NAME ($REMOTE_URL)"
      git push "$REMOTE_NAME" HEAD
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["push"]
    
    context = {
        "vars": {
            "REMOTE_NAME": "direct",
            "REMOTE_URL": "ssh://user@server/repo.git",
            "PUSH_ON_RUN": "true"
        },
        "inputs": {},
        "env": {}
    }
    compiled = interpolate(script.run, context)
    
    assert 'REMOTE_NAME="direct"' in compiled
    assert 'REMOTE_URL="ssh://user@server/repo.git"' in compiled
    assert 'git push "$REMOTE_NAME" HEAD' in compiled


def test_compile_multiline_script():
    """Test compiling a multi-line script as list."""
    yaml_str = """
name: test
tags: [test]
vars:
  MSG: "Hello"
scripts:
  multi:
    run:
      - echo "${{ vars.MSG }}"
      - echo "Line 2"
      - echo "Line 3"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["multi"]
    
    # When run is a list, it should be joined with newlines
    run_str = "\n".join(script.run)
    context = {"vars": {"MSG": "Greetings"}, "inputs": {}, "env": {}}
    compiled = interpolate(run_str, context)
    
    assert 'echo "Greetings"' in compiled
    assert 'echo "Line 2"' in compiled
    assert 'echo "Line 3"' in compiled


def test_bash_special_chars_preserved():
    """Test that bash special characters are preserved in non-template parts."""
    yaml_str = """
name: test
tags: [test]
vars:
  FILE: "test.txt"
scripts:
  complex:
    run: |
      #!/usr/bin/env bash
      set -euo pipefail
      
      FILE="${{ vars.FILE }}"
      
      # Bash substitutions should work
      if [ -f "$FILE" ]; then
        echo "File exists"
      fi
      
      # Parameter expansion
      echo "${HOME}"
      echo "$(date)"
"""
    comp = load_component_from_string(yaml_str)
    script = comp.scripts["complex"]
    
    context = {"vars": {"FILE": "output.log"}, "inputs": {}, "env": {}}
    compiled = interpolate(script.run, context)
    
    # Template var should be interpolated
    assert 'FILE="output.log"' in compiled
    
    # Bash vars should remain
    assert '${HOME}' in compiled or '$HOME' in compiled
    assert '$(date)' in compiled
    
    # Bash conditionals should remain
    assert 'if [ -f "$FILE" ]; then' in compiled
    assert 'echo "File exists"' in compiled
