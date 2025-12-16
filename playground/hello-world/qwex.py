from dataclasses import dataclass, field
from jinja2 import Environment


@dataclass
class ModuleInclude:
    source: str
    vars: dict[str, str] = field(default_factory=dict)


@dataclass
class TaskSpec:
    run: str
    args: dict[str, str] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)


@dataclass
class ModuleSpec:
    name: str
    includes: dict[str, ModuleInclude] = field(default_factory=dict)
    vars: dict[str, str] = field(default_factory=dict)
    tasks: dict[str, TaskSpec] = field(default_factory=dict)


SLURM_MODULE = ModuleSpec(
    name="slurm",
    vars={
        "job_name": "hello_world",
        "output_file": "hello_world.out",
        "error_file": "hello_world.err",
        "time_limit": "01:00:00",
        "cpus_per_task": "1",
        "memory": "1G",
    },
    tasks={
        "sbatch": TaskSpec(
            args={"command": "echo 'Hello, World!'"},
            run=(
                "sbatch --job-name={{ vars.job_name }} \\\n"
                "       --output={{ vars.output_file }} \\\n"
                "       --error={{ vars.error_file }} \\\n"
                "       --time={{ vars.time_limit }} \\\n"
                "       --cpus-per-task={{ vars.cpus_per_task }} \\\n"
                "       --mem={{ vars.memory }} \\\n"
                '       --wrap="{{ args.command }}"'
            ),
        )
    },
)

SSH_MODULE = ModuleSpec(
    name="ssh",
    vars={"host": "csc"},
    tasks={
        "exec": TaskSpec(
            args={"command": "ls -la"},
            run='ssh {{ vars.host }} "$@"',
        )
    },
)

ROOT_MODULE = ModuleSpec(
    name="main",
    includes={
        "slurm": ModuleInclude(source="slurm"),
        "ssh": ModuleInclude(source="ssh"),
    },
    tasks={
        "remote_slurm": TaskSpec(
            args={"command": "echo 'Hello from SLURM'"},
            run=r"""{{ call.ssh.exec }} bash -s -- "$@" << REMOTE_EOF
{{ source.slurm.sbatch }}
slurm__sbatch "\$@"
REMOTE_EOF""",
        )
    },
)

MODULE_REGISTRY: dict[str, ModuleSpec] = {
    "main": ROOT_MODULE,
    "slurm": SLURM_MODULE,
    "ssh": SSH_MODULE,
}


@dataclass
class CompiledFunction:
    namespace: str
    name: str
    body: str

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}__{self.name}" if self.namespace else self.name

    @property
    def source_expr(self) -> str:
        return f"$(declare -f {self.qualified_name})"


@dataclass
class CompiledModule:
    functions: dict[str, CompiledFunction]
    dependencies: dict[str, "CompiledModule"]


class Compiler:
    def __init__(self, registry: dict[str, ModuleSpec]):
        self.registry = registry
        self.env = Environment()
        self.compiled_cache: dict[str, CompiledModule] = {}

    def compile_module(self, module_name: str, namespace: str = "") -> CompiledModule:
        cache_key = f"{namespace}:{module_name}"
        if cache_key in self.compiled_cache:
            return self.compiled_cache[cache_key]

        module = self.registry[module_name]
        dependencies: dict[str, CompiledModule] = {}

        for alias, include in module.includes.items():
            child_ns = f"{namespace}__{alias}" if namespace else alias
            dependencies[alias] = self.compile_module(include.source, child_ns)

        refs = self._build_refs(dependencies)

        functions: dict[str, CompiledFunction] = {}
        for task_name, task in module.tasks.items():
            body = self._render_task(module, task, refs)
            functions[task_name] = CompiledFunction(
                namespace=namespace, name=task_name, body=body
            )

        compiled = CompiledModule(functions=functions, dependencies=dependencies)
        self.compiled_cache[cache_key] = compiled
        return compiled

    def _build_refs(
        self, deps: dict[str, CompiledModule]
    ) -> dict[str, dict[str, CompiledFunction]]:
        return {alias: dep.functions for alias, dep in deps.items()}

    def _render_task(
        self,
        module: ModuleSpec,
        task: TaskSpec,
        refs: dict[str, dict[str, CompiledFunction]],
    ) -> str:
        call_refs = {
            alias: {name: fn.qualified_name for name, fn in fns.items()}
            for alias, fns in refs.items()
        }
        source_refs = {
            alias: {name: fn.source_expr for name, fn in fns.items()}
            for alias, fns in refs.items()
        }
        args = self._process_args(task.args)
        merged_vars = {**module.vars, **task.vars}
        template = self.env.from_string(task.run)
        return template.render(
            vars=merged_vars, args=args, call=call_refs, source=source_refs
        )

    def _process_args(self, args_spec: dict[str, str]) -> dict[str, str]:
        processed: dict[str, str] = {}
        for idx, (key, default) in enumerate(args_spec.items()):
            if key.startswith("*"):
                processed[key.lstrip("*")] = '"$@"'
            else:
                processed[key] = f'${{{idx + 1}:-"{default}"}}'
        return processed


class Renderer:
    def __init__(self, compiled: CompiledModule):
        self.compiled = compiled

    def render(self) -> str:
        lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        self._render_module(self.compiled, lines, set())
        lines.append('"$@"')
        return "\n".join(lines)

    def _render_module(
        self,
        module: CompiledModule,
        lines: list[str],
        rendered: set[str],
    ) -> None:
        for dep in module.dependencies.values():
            self._render_module(dep, lines, rendered)

        for fn in module.functions.values():
            if fn.qualified_name in rendered:
                continue
            rendered.add(fn.qualified_name)
            lines.append(f"{fn.qualified_name}() {{")
            for line in fn.body.strip().splitlines():
                lines.append(f"    {line}")
            lines.append("}")
            lines.append("")


compiler = Compiler(MODULE_REGISTRY)
compiled = compiler.compile_module("main")
renderer = Renderer(compiled)
print(renderer.render())
