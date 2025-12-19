"""Tests for shell() and include_file() compile-time functions."""

import pytest
from pathlib import Path
import tempfile
import os

from qwl.compiler import Compiler
from qwl.compiler.renderer import Renderer
from qwl.ast import Parser


def test_shell_function():
    """Test that shell() executes at compile time."""
    yaml_content = """
name: test
tasks:
  show:
    run: |
      echo "{{ shell('echo hello') }}"
"""
    parser = Parser()
    mod = parser.parse(yaml_content)
    comp = Compiler()
    script = comp.compile(mod)

    for fn in script.functions:
        if fn.name == "show":
            assert "hello" in fn.body
            assert "shell(" not in fn.body  # Evaluated at compile time


def test_include_file():
    """Test that include_file() includes file contents at compile time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        qwex_path = Path(tmpdir) / "qwex.yaml"
        data_path = Path(tmpdir) / "data.txt"

        data_path.write_text("Line 1\nLine 2\nLine 3")
        qwex_path.write_text("""
name: test
tasks:
  show:
    run: |
      cat <<HEREDOC
      {{ include_file("data.txt", __srcdir__) }}
      HEREDOC
""")

        parser = Parser()
        mod = parser.parse_file(str(qwex_path))
        comp = Compiler(base_dir=Path(tmpdir))
        script = comp.compile(mod)

        for fn in script.functions:
            if fn.name == "show":
                assert "Line 1" in fn.body
                assert "Line 2" in fn.body
                assert "Line 3" in fn.body
                assert "include_file" not in fn.body  # Evaluated at compile time


def test_source_dir_in_root_module():
    """Test that __srcdir__ is set correctly for root module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        qwex_path = Path(tmpdir) / "qwex.yaml"
        qwex_path.write_text("""
name: test
tasks:
  show:
    run: |
      echo "Source: {{ __srcdir__ }}"
""")

        parser = Parser()
        mod = parser.parse_file(str(qwex_path))
        comp = Compiler(base_dir=Path(tmpdir))
        script = comp.compile(mod)

        for fn in script.functions:
            if fn.name == "show":
                assert tmpdir in fn.body


def test_source_dir_in_imported_module():
    """Test that __srcdir__ is set correctly for imported modules."""
    parser = Parser()
    mod = parser.parse("""
name: test
modules:
  log:
    source: std/log
tasks:
  greet:
    run: echo "hi"
""")
    comp = Compiler(base_dir=Path.cwd())
    env_tree = comp.resolver.resolve(mod)

    # Root module should have cwd as source_dir
    assert "__srcdir__" in env_tree

    # Log module should have builtins/std as source_dir
    assert "__srcdir__" in env_tree.get("log", {})
    assert "builtins/std" in env_tree["log"]["__srcdir__"]


def test_shell_with_cwd():
    """Test that shell() can use __srcdir__ as cwd."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a subdirectory with a file
        subdir = Path(tmpdir) / "subdir"
        subdir.mkdir()
        (subdir / "version.txt").write_text("1.0.0")

        qwex_path = Path(tmpdir) / "qwex.yaml"
        qwex_path.write_text("""
name: test
tasks:
  show:
    run: |
      echo "Version: {{ shell('cat subdir/version.txt', cwd=__srcdir__) }}"
""")

        parser = Parser()
        mod = parser.parse_file(str(qwex_path))
        comp = Compiler(base_dir=Path(tmpdir))
        script = comp.compile(mod)

        for fn in script.functions:
            if fn.name == "show":
                assert "1.0.0" in fn.body
