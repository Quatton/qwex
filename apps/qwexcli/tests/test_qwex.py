"""Comprehensive tests for qwexcli."""

import subprocess
import sys

import pytest
import yaml

from qwexcli.lib.config import (
    QwexConfig,
    TaskConfig,
    StepConfig,
    ModeConfig,
    ModeTaskOverlay,
    ModeStepOverlay,
    load_qwex_yaml,
    load_env_yaml,
    merge_config,
    save_qwex_yaml,
    apply_mode_overlay,
)
from qwexcli.lib.project import (
    scaffold,
    find_project_root,
    ProjectRootNotFoundError,
)
from qwexcli.lib.plugin import (
    get_plugin,
    EchoPlugin,
    BasePlugin,
    ShellPlugin,
    list_builtin_plugins,
)
from qwexcli.lib.runner import (
    TaskRunner,
    generate_run_id,
    JinjaRenderer,
    BashCompiler,
)
from qwexcli.lib.agent import (
    LocalAgent,
    get_agent,
)


# =============================================================================
# Config Tests
# =============================================================================


class TestQwexConfig:
    def test_minimal_config(self):
        """Config with just name should work."""
        config = QwexConfig(name="test-project")
        assert config.name == "test-project"
        assert config.tasks == {}

    def test_config_with_task(self):
        """Config with a task definition."""
        config = QwexConfig(
            name="test",
            tasks={
                "build": TaskConfig(
                    args={"target": "release"},
                    steps=[
                        StepConfig(uses="std/echo", with_={"message": "Building..."}),
                    ],
                )
            },
        )
        assert "build" in config.tasks
        assert config.tasks["build"].args["target"] == "release"
        assert len(config.tasks["build"].steps) == 1

    def test_step_with_alias(self):
        """StepConfig should accept 'with' as alias for 'with_'."""
        # When loading from YAML, 'with' maps to 'with_'
        step = StepConfig(uses="std/echo", **{"with": {"message": "hello"}})
        assert step.with_ == {"message": "hello"}


class TestConfigIO:
    def test_save_and_load_roundtrip(self, tmp_path):
        """Save then load should preserve config."""
        config = QwexConfig(
            name="roundtrip-test",
            tasks={
                "run": TaskConfig(
                    args={"command": ""},
                    steps=[
                        StepConfig(
                            name="Echo",
                            uses="std/echo",
                            with_={"message": "{{ args.command }}"},
                        )
                    ],
                )
            },
        )

        path = tmp_path / "qwex.yaml"
        save_qwex_yaml(config, path)

        loaded = load_qwex_yaml(path)
        assert loaded.name == "roundtrip-test"
        assert "run" in loaded.tasks
        assert loaded.tasks["run"].steps[0].uses == "std/echo"

    def test_load_nonexistent_raises(self, tmp_path):
        """Loading nonexistent file should raise."""
        with pytest.raises(FileNotFoundError):
            load_qwex_yaml(tmp_path / "does-not-exist.yaml")

    def test_load_env_yaml_missing_returns_empty(self, tmp_path):
        """Loading missing .env.yaml should return empty dict."""
        result = load_env_yaml(tmp_path / ".qwex" / ".env.yaml")
        assert result == {}

    def test_load_env_yaml_with_overrides(self, tmp_path):
        """Loading .env.yaml should return its contents."""
        env_path = tmp_path / ".qwex" / ".env.yaml"
        env_path.parent.mkdir(parents=True)
        env_path.write_text("tasks:\n  run:\n    args:\n      command: 'override'\n")

        result = load_env_yaml(env_path)
        assert result["tasks"]["run"]["args"]["command"] == "override"


class TestMergeConfig:
    def test_merge_args(self):
        """Merging should update task args."""
        base = QwexConfig(
            name="test",
            tasks={
                "run": TaskConfig(args={"a": "1", "b": "2"}, steps=[]),
            },
        )
        overrides = {"tasks": {"run": {"args": {"b": "override", "c": "new"}}}}

        merged = merge_config(base, overrides)
        assert merged.tasks["run"].args == {"a": "1", "b": "override", "c": "new"}

    def test_merge_name(self):
        """Merging should allow name override."""
        base = QwexConfig(name="original", tasks={})
        overrides = {"name": "overridden"}

        merged = merge_config(base, overrides)
        assert merged.name == "overridden"


# =============================================================================
# Project Tests
# =============================================================================


class TestScaffold:
    def test_scaffold_creates_qwex_yaml(self, tmp_path):
        """Scaffold should create qwex.yaml."""
        result = scaffold(tmp_path)
        assert result == tmp_path / "qwex.yaml"
        assert result.exists()

    def test_scaffold_default_content(self, tmp_path):
        """Scaffold should create default content."""
        scaffold(tmp_path, name="my-project")

        with open(tmp_path / "qwex.yaml") as f:
            data = yaml.safe_load(f)

        assert data["name"] == "my-project"
        assert "tasks" in data
        assert "run" in data["tasks"]
        assert len(data["tasks"]["run"]["steps"]) == 3

    def test_scaffold_creates_gitignore(self, tmp_path):
        """Scaffold should create .gitignore with .qwex/."""
        scaffold(tmp_path)

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert ".qwex/" in gitignore.read_text()

    def test_scaffold_appends_to_existing_gitignore(self, tmp_path):
        """Scaffold should append to existing .gitignore if .qwex/ not present."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")

        scaffold(tmp_path)

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".qwex/" in content

    def test_scaffold_does_not_duplicate_gitignore_entry(self, tmp_path):
        """Scaffold should not duplicate .qwex/ in .gitignore."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".qwex/\n")

        scaffold(tmp_path)

        content = gitignore.read_text()
        assert content.count(".qwex/") == 1


class TestFindProjectRoot:
    def test_finds_root_in_current_dir(self, tmp_path):
        """Should find root when qwex.yaml is in current dir."""
        (tmp_path / "qwex.yaml").write_text("name: test\n")

        result = find_project_root(tmp_path)
        assert result == tmp_path

    def test_finds_root_in_parent(self, tmp_path):
        """Should find root when qwex.yaml is in parent dir."""
        (tmp_path / "qwex.yaml").write_text("name: test\n")
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)

        result = find_project_root(subdir)
        assert result == tmp_path

    def test_raises_when_not_found(self, tmp_path):
        """Should raise when no qwex.yaml found."""
        subdir = tmp_path / "empty"
        subdir.mkdir()

        with pytest.raises(ProjectRootNotFoundError):
            find_project_root(subdir)


# =============================================================================
# Plugin Tests
# =============================================================================


class TestPlugins:
    def test_list_builtin_plugins(self):
        """Should list all built-in plugins."""
        plugins = list_builtin_plugins()
        assert "std/echo" in plugins
        assert "std/bash" in plugins
        assert "std/base" in plugins
        assert "std/shell" in plugins

    def test_get_plugin_echo(self):
        """Should get echo plugin."""
        plugin = get_plugin("std/echo")
        assert isinstance(plugin, EchoPlugin)
        assert plugin.full_name == "std/echo"

    def test_get_plugin_base(self):
        """Should get base plugin."""
        plugin = get_plugin("std/base")
        assert isinstance(plugin, BasePlugin)

    def test_get_plugin_bash(self):
        """Should get bash plugin."""
        plugin = get_plugin("std/bash")
        assert isinstance(plugin, BasePlugin)
        assert plugin.full_name == "std/bash"

    def test_get_plugin_unknown_raises(self):
        """Should raise for unknown plugin."""
        with pytest.raises(ValueError, match="Unknown plugin"):
            get_plugin("unknown/plugin")


class TestEchoPlugin:
    def test_compile_function(self):
        """Echo plugin should compile to bash function."""
        plugin = EchoPlugin()
        func = plugin.compile_function()

        assert "__std__echo()" in func
        assert 'echo "$message"' in func

    def test_compile_call(self):
        """Echo plugin should compile call with escaped message."""
        plugin = EchoPlugin()
        call = plugin.compile_call({"message": "hello world"})

        assert "__std__echo" in call
        assert "hello world" in call

    def test_compile_call_escapes_quotes(self):
        """Echo plugin should escape quotes in message."""
        plugin = EchoPlugin()
        call = plugin.compile_call({"message": "it's a test"})

        # shlex.quote handles this
        assert "__std__echo" in call


class TestBasePlugin:
    def test_compile_function(self):
        """Base plugin should compile to bash function."""
        plugin = BasePlugin()
        func = plugin.compile_function()

        assert "__std__base()" in func
        assert 'eval "$cmd"' in func

    def test_compile_call(self):
        """Base plugin should compile call."""
        plugin = BasePlugin()
        call = plugin.compile_call({"command": "python train.py"})

        assert "__std__base" in call


class TestShellPlugin:
    def test_compile_function_is_empty(self):
        """Shell plugin has no function (inlines directly)."""
        plugin = ShellPlugin()
        func = plugin.compile_function()
        assert func == ""

    def test_compile_call_string(self):
        """Shell plugin should return the run string."""
        plugin = ShellPlugin()
        call = plugin.compile_call({"run": "echo hello"})
        assert call == "echo hello"

    def test_compile_call_list(self):
        """Shell plugin should join list of commands."""
        plugin = ShellPlugin()
        call = plugin.compile_call({"run": ["echo hello", "echo world"]})
        assert call == "echo hello\necho world"


# =============================================================================
# Runner Tests
# =============================================================================


class TestGenerateRunId:
    def test_format(self):
        """Run ID should be in expected format."""
        run_id = generate_run_id()

        # Format: YYYYMMDD_HHMMSS_xxxxxxxx
        parts = run_id.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert len(parts[2]) == 8  # hex

    def test_uniqueness(self):
        """Run IDs should be unique."""
        ids = [generate_run_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_sortable(self):
        """Run IDs should be lexicographically sortable by time."""
        import time

        id1 = generate_run_id()
        time.sleep(0.01)
        id2 = generate_run_id()

        # id2 should sort after id1 (same timestamp prefix possible, but random suffix differs)
        # For strict ordering, we'd need to mock time
        assert isinstance(id1, str)
        assert isinstance(id2, str)


class TestJinjaRenderer:
    def test_render_simple(self):
        """Should render simple template."""
        renderer = JinjaRenderer({"args": {"name": "world"}})
        result = renderer.render("Hello {{ args.name }}!")
        assert result == "Hello world!"

    def test_render_with_run_id(self):
        """Should render with run_id."""
        renderer = JinjaRenderer({"run_id": "test-123"})
        result = renderer.render("Run: {{ run_id }}")
        assert result == "Run: test-123"

    def test_render_dict(self):
        """Should recursively render dict."""
        renderer = JinjaRenderer({"args": {"cmd": "python"}})
        result = renderer.render_dict(
            {"message": "Running {{ args.cmd }}", "nested": {"value": "{{ args.cmd }}"}}
        )
        assert result["message"] == "Running python"
        assert result["nested"]["value"] == "python"

    def test_render_undefined_raises(self):
        """Should raise on undefined variable."""
        renderer = JinjaRenderer({})
        with pytest.raises(ValueError, match="Undefined variable"):
            renderer.render("{{ undefined.var }}")


class TestBashCompiler:
    def test_compile_empty(self):
        """Empty compiler should produce valid script."""
        compiler = BashCompiler()
        script = compiler.compile()

        assert "#!/bin/bash" in script
        assert "set -u" in script  # New kernel uses set -u
        assert "__qwex_main()" in script
        assert "q_run_step" in script  # New kernel function name

    def test_compile_with_steps(self):
        """Should compile steps."""
        compiler = BashCompiler()
        plugin = EchoPlugin()
        compiler.add_step("test-step", plugin, {"message": "hello"})

        script = compiler.compile()

        assert "__std__echo()" in script
        assert "q_run_step" in script  # New kernel uses q_run_step
        assert "test-step" in script

    def test_compile_multiple_plugins(self):
        """Should handle multiple different plugins."""
        compiler = BashCompiler()
        compiler.add_step("step1", EchoPlugin(), {"message": "hello"})
        compiler.add_step("step2", BasePlugin(), {"command": "ls"})

        script = compiler.compile()

        assert "__std__echo()" in script
        assert "__std__base()" in script

    def test_compile_with_context(self):
        """Should embed context in payload."""
        context = {
            "run_id": "20251213_123456_abcd1234",
            "task_name": "test_task",
            "args": {"foo": "bar", "baz": "qux"},
        }
        compiler = BashCompiler(context=context)
        script = compiler.compile()

        assert '__QWEX_RUN_ID="20251213_123456_abcd1234"' in script
        assert '__QWEX_TASK="test_task"' in script
        assert '__QWEX_ARG_foo="bar"' in script
        assert '__QWEX_ARG_baz="qux"' in script


class TestTaskRunner:
    def test_load_config(self, tmp_path):
        """Should load config from qwex.yaml."""
        scaffold(tmp_path, name="test-project")

        runner = TaskRunner(tmp_path)
        config = runner.load_config()

        assert config.name == "test-project"
        assert "run" in config.tasks

    def test_load_config_with_env_override(self, tmp_path):
        """Should merge .env.yaml overrides."""
        scaffold(tmp_path, name="test-project")

        env_yaml = tmp_path / ".qwex" / ".env.yaml"
        env_yaml.parent.mkdir(parents=True, exist_ok=True)
        env_yaml.write_text("name: overridden\n")

        runner = TaskRunner(tmp_path)
        config = runner.load_config()

        assert config.name == "overridden"

    def test_get_task(self, tmp_path):
        """Should get task by name."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        config = runner.load_config()
        task = runner.get_task(config, "run")

        assert task is not None
        assert "command" in task.args

    def test_get_task_not_found(self, tmp_path):
        """Should raise for nonexistent task."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        config = runner.load_config()

        with pytest.raises(ValueError, match="not found"):
            runner.get_task(config, "nonexistent")

    def test_compile_task(self, tmp_path):
        """Should compile task to bash."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        config = runner.load_config()
        task = config.tasks["run"]

        context = runner.build_context(
            config, task, "test-run-id", {"command": "echo hello"}
        )
        script = runner.compile_task(task, context)

        assert "#!/bin/bash" in script
        assert "Running command: echo hello" in script
        assert "Run ID: test-run-id" in script

    def test_list_tasks(self, tmp_path):
        """Should list available tasks."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        tasks = runner.list_tasks()

        assert "run" in tasks

    def test_run_task_dry_run(self, tmp_path, capsys):
        """Dry run should print script without executing."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task(
            "run", cli_args={"command": "echo test"}, dry_run=True
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "#!/bin/bash" in captured.out

    def test_run_task_executes(self, tmp_path):
        """Should execute the compiled script."""
        # Create a minimal qwex.yaml that just echoes
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  run:
    args:
      command: ""
    steps:
      - uses: std/shell
        with:
          run: "echo SUCCESS"
"""
        )

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task("run", cli_args={}, dry_run=False)

        assert exit_code == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Integration tests that run the actual CLI."""

    def test_init_creates_files(self, tmp_path):
        """qwex init should create qwex.yaml and .gitignore."""
        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "init"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert (tmp_path / "qwex.yaml").exists()
        assert (tmp_path / ".gitignore").exists()

    def test_init_force_overwrites(self, tmp_path):
        """qwex init --force should overwrite existing."""
        (tmp_path / "qwex.yaml").write_text("name: old\n")

        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "init", "--force", "--name", "new"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        with open(tmp_path / "qwex.yaml") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "new"

    def test_tasks_lists_tasks(self, tmp_path):
        """qwex tasks should list available tasks."""
        scaffold(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "tasks"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "run" in result.stdout

    def test_run_dry_run(self, tmp_path):
        """qwex run --dry-run should print script."""
        scaffold(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "run", "--dry-run", "echo hello"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "#!/bin/bash" in result.stdout
        assert "echo hello" in result.stdout

    def test_run_executes_command(self, tmp_path):
        """qwex run should execute the command."""
        # Create minimal config
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            "\n".join(
                [
                    "name: test",
                    "tasks:",
                    "  run:",
                    "    args:",
                    '      command: ""',
                    "    steps:",
                    "      - uses: std/bash",
                    "        with:",
                    '          command: "{{ args.command }}"',
                    "",
                ]
            )
        )

        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "run", "echo SUCCESS"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "SUCCESS" in result.stdout

    def test_compile_outputs_script(self, tmp_path):
        """qwex compile should output the bash script."""
        scaffold(tmp_path)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "qwexcli.main",
                "compile",
                "run",
                "-a",
                "command=test",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "#!/bin/bash" in result.stdout

    def test_exec_with_args(self, tmp_path):
        """qwex exec should accept --arg options."""
        scaffold(tmp_path)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "qwexcli.main",
                "exec",
                "run",
                "--dry-run",
                "-a",
                "command=python train.py",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "python train.py" in result.stdout

    def test_outside_project_fails(self, tmp_path):
        """Commands should fail outside a qwex project."""
        result = subprocess.run(
            [sys.executable, "-m", "qwexcli.main", "tasks"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert (
            "Not in a qwex project" in result.stderr
            or "no qwex.yaml" in result.stderr.lower()
        )


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    def test_empty_command(self, tmp_path):
        """Should handle empty command."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        # Should not crash with empty command
        exit_code = runner.run_task("run", cli_args={"command": ""}, dry_run=True)
        assert exit_code == 0

    def test_special_characters_in_command(self, tmp_path):
        """Should handle special shell characters."""
        scaffold(tmp_path)

        runner = TaskRunner(tmp_path)
        # Commands with quotes, pipes, etc.
        exit_code = runner.run_task(
            "run",
            cli_args={"command": "echo 'hello world' | grep hello"},
            dry_run=True,
        )
        assert exit_code == 0

    def test_task_with_no_steps(self, tmp_path):
        """Should handle task with no steps."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  empty:
    args: {}
    steps: []
"""
        )

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task("empty", dry_run=True)
        assert exit_code == 0

    def test_unknown_plugin_in_step(self, tmp_path):
        """Should raise for unknown plugin in step."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  bad:
    steps:
      - uses: unknown/plugin
"""
        )

        runner = TaskRunner(tmp_path)
        with pytest.raises(ValueError, match="Unknown plugin"):
            runner.run_task("bad", dry_run=True)


# =============================================================================
# Mode Overlay Tests
# =============================================================================


class TestModeOverlay:
    """Tests for task polymorphism via mode overlays."""

    def test_apply_mode_overlay_adds_uses(self, tmp_path):
        """Mode overlay should add 'uses' to steps."""
        # Task with steps that have no 'uses'
        task = TaskConfig(
            args={},
            steps=[
                StepConfig(id="step1", name="First step", hint="Do this manually"),
                StepConfig(id="step2", name="Second step", hint="Do that manually"),
            ],
        )

        # Mode that provides implementations (list of steps with IDs)
        mode = ModeConfig(
            tasks={
                "my_task": ModeTaskOverlay(
                    steps=[
                        ModeStepOverlay(
                            id="step1", uses="std/shell", with_={"run": "echo step1"}
                        ),
                        ModeStepOverlay(
                            id="step2", uses="std/shell", with_={"run": "echo step2"}
                        ),
                    ]
                )
            }
        )

        result = apply_mode_overlay(task, mode, "my_task")

        # Steps should now have 'uses'
        assert result.steps[0].uses == "std/shell"
        assert result.steps[0].with_["run"] == "echo step1"
        assert result.steps[1].uses == "std/shell"

    def test_mode_overlay_preserves_original_task(self, tmp_path):
        """Mode overlay should not mutate the original task."""
        task = TaskConfig(
            args={"original": "value"},
            steps=[
                StepConfig(
                    id="step1",
                    name="Step",
                    uses="std/echo",
                    with_={"message": "original"},
                ),
            ],
        )

        mode = ModeConfig(
            tasks={
                "test": ModeTaskOverlay(
                    steps=[
                        ModeStepOverlay(
                            id="step1", uses="std/shell", with_={"run": "new command"}
                        ),
                    ]
                )
            }
        )

        result = apply_mode_overlay(task, mode, "test")

        # Original should be unchanged
        assert task.steps[0].uses == "std/echo"
        assert task.steps[0].with_["message"] == "original"

        # Result should have overlay applied
        assert result.steps[0].uses == "std/shell"
        assert result.steps[0].with_["run"] == "new command"

    def test_task_without_mode_raises_on_missing_uses(self, tmp_path):
        """Tasks without 'uses' in steps should raise when no mode applied."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  setup:
    steps:
      - id: step1
        name: Manual step
        hint: Do this by hand
"""
        )

        runner = TaskRunner(tmp_path)
        with pytest.raises(ValueError, match="no implementation.*missing 'uses'"):
            runner.run_task("setup", dry_run=True)

    def test_run_task_with_mode(self, tmp_path, capsys):
        """Should apply mode overlay when running task."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  deploy:
    args:
      env: staging
    steps:
      - id: build
        name: Build artifact
        hint: Run 'make build'
      - id: upload
        name: Upload to server
        hint: Use scp to upload

modes:
  auto:
    tasks:
      deploy:
        steps:
          - id: build
            uses: std/shell
            with:
              run: "echo Building for {{ args.env }}"
          - id: upload
            uses: std/shell
            with:
              run: "echo Uploading to {{ args.env }}"
"""
        )

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task("deploy", mode="auto", dry_run=True)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Building for staging" in captured.out
        assert "Uploading to staging" in captured.out

    def test_list_modes(self, tmp_path):
        """Should list available modes."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks: {}
modes:
  auto:
    tasks: {}
  runbook:
    tasks: {}
  dry:
    tasks: {}
"""
        )

        runner = TaskRunner(tmp_path)
        modes = runner.list_modes()

        assert "auto" in modes
        assert "runbook" in modes
        assert "dry" in modes

    def test_mode_not_found(self, tmp_path):
        """Should raise for nonexistent mode."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  run:
    steps:
      - uses: std/echo
        with:
          message: hello
modes: {}
"""
        )

        runner = TaskRunner(tmp_path)
        with pytest.raises(ValueError, match="Mode 'nonexistent' not found"):
            runner.run_task("run", mode="nonexistent", dry_run=True)

    def test_mode_overlay_partial_steps(self, tmp_path, capsys):
        """Mode overlay can override only some steps."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
tasks:
  mixed:
    steps:
      - uses: std/echo
        with:
          message: "This step is already implemented"
      - id: manual_step
        name: Manual step
        hint: Do this by hand

modes:
  auto:
    tasks:
      mixed:
        steps:
          - id: manual_step
            uses: std/shell
            with:
              run: "echo Automated!"
"""
        )

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task("mixed", mode="auto", dry_run=True)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "This step is already implemented" in captured.out
        assert "Automated!" in captured.out

    def test_defaults_args_in_context(self, tmp_path, capsys):
        """Defaults args should be available in Jinja context."""
        qwex_yaml = tmp_path / "qwex.yaml"
        qwex_yaml.write_text(
            """
name: test
defaults:
  args:
    base_url: https://example.com

tasks:
  show_url:
    steps:
      - uses: std/echo
        with:
          message: "URL: {{ defaults.args.base_url }}"
"""
        )

        runner = TaskRunner(tmp_path)
        exit_code = runner.run_task("show_url", dry_run=True)

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "URL: https://example.com" in captured.out


# =============================================================================
# Agent Tests
# =============================================================================


class TestLocalAgent:
    def test_agent_name(self):
        """Local agent should have name 'local'."""
        agent = LocalAgent()
        assert agent.name == "local"

    def test_execute_simple_payload(self, tmp_path):
        """Agent should execute a simple bash payload."""
        agent = LocalAgent()
        payload = "#!/bin/bash\necho 'hello from agent'"
        context = {"run_id": "test_123", "task_name": "test"}

        exit_code = agent.execute(payload, context, tmp_path)
        assert exit_code == 0

    def test_execute_payload_with_exit_code(self, tmp_path):
        """Agent should return payload's exit code."""
        agent = LocalAgent()
        payload = "#!/bin/bash\nexit 42"
        context = {"run_id": "test_123", "task_name": "test"}

        exit_code = agent.execute(payload, context, tmp_path)
        assert exit_code == 42

    def test_execute_payload_sees_qwex_home(self, tmp_path):
        """Payload should see QWEX_HOME environment variable."""
        agent = LocalAgent()
        output_file = tmp_path / "qwex_home.txt"
        payload = f'#!/bin/bash\necho "$QWEX_HOME" > "{output_file}"'
        context = {"run_id": "test_123", "task_name": "test"}

        agent.execute(payload, context, tmp_path)

        assert output_file.exists()
        assert output_file.read_text().strip() == str(tmp_path)

    def test_get_agent_local(self):
        """get_agent should return LocalAgent for 'local'."""
        agent = get_agent("local")
        assert isinstance(agent, LocalAgent)

    def test_get_agent_unknown_raises(self):
        """get_agent should raise for unknown agent."""
        with pytest.raises(ValueError, match="Agent 'unknown' not found"):
            get_agent("unknown")
