from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleRef:
    """Reference to an external module to import."""

    name: str
    source: str
    vars: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """A task is a unit of work that can be executed."""

    name: str
    run: Optional[str] = None
    vars: Dict[str, Any] = field(default_factory=dict)
    env: Dict[str, str] = field(default_factory=dict)
    uses: Optional[str] = None
    with_: List[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, d: Any) -> "Task":
        if isinstance(d, str):
            return cls(name=name, run=d)

        if not isinstance(d, dict):
            raise TypeError(f"Task '{name}' must be a mapping or string")

        run = d.get("run")
        vars = d.get("vars") or {}
        env = d.get("env") or {}
        uses = d.get("uses")
        with_ = d.get("with") or []

        if run is None:
            run_val = None
        else:
            run_val = str(run)

        if not isinstance(vars, (dict, list)):
            raise TypeError(f"Task '{name}' 'vars' must be a mapping or list")
        if not isinstance(env, dict):
            raise TypeError(f"Task '{name}' 'env' must be a mapping")

        return cls(
            name=name,
            run=run_val,
            vars=dict(vars) if isinstance(vars, dict) else {},
            env=dict(env),
            uses=uses,
            with_=with_,
        )


@dataclass
class PartialModule:
    """This is a PartialModule used for presets, which can be merged into a full Module depending on the compile flags."""

    name: str
    vars: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, Task] = field(default_factory=dict)
    modules: Dict[str, ModuleRef] = field(default_factory=dict)
    includes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "PartialModule":
        if not isinstance(d, dict):
            raise TypeError(f"PartialModule '{name}' must be a mapping")

        vars_ = d.get("vars") or {}
        includes_ = d.get("includes") or []
        tasks_ = d.get("tasks") or {}
        modules_ = d.get("modules") or {}

        if not isinstance(vars_, dict):
            raise TypeError(f"PartialModule '{name}' 'vars' must be a mapping")
        if not isinstance(includes_, list):
            raise TypeError(f"PartialModule '{name}' 'includes' must be a list")
        if not isinstance(tasks_, dict):
            raise TypeError(f"PartialModule '{name}' 'tasks' must be a mapping")
        if not isinstance(modules_, dict):
            raise TypeError(f"PartialModule '{name}' 'modules' must be a mapping")

        tasks: Dict[str, Task] = {}
        for tname, td in tasks_.items():
            tasks[tname] = Task.from_dict(tname, td)

        modules: Dict[str, ModuleRef] = {}
        for mname, md in modules_.items():
            if isinstance(md, dict) and "source" in md:
                modules[mname] = ModuleRef(name=mname, source=md["source"])
            else:
                raise ValueError(
                    f"PartialModule '{name}' module '{mname}' must have 'source' field"
                )

        return cls(
            name=name,
            vars=dict(vars_),
            tasks=tasks,
            modules=modules,
            includes=list(includes_),
        )


@dataclass
class Module(PartialModule):
    """A module is the root unit containing tasks, vars, imports, and also presets."""

    presets: Dict[str, PartialModule] = field(default_factory=dict)
    defaults: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        if not isinstance(d, dict):
            raise TypeError("Module.from_dict expects a mapping")

        name = d.get("name") or "main"

        partial = PartialModule.from_dict(name, d)

        vars_ = partial.vars
        includes = partial.includes
        tasks = partial.tasks
        modules = partial.modules

        presets_config = d.get("presets") or {}
        defaults_ = d.get("defaults") or []

        if not isinstance(presets_config, dict):
            raise TypeError("Module 'presets' must be a mapping")

        modules: Dict[str, ModuleRef] = {}

        presets: Dict[str, PartialModule] = {}
        for pname, pd in presets_config.items():
            presets[pname] = PartialModule.from_dict(pname, pd)

        return cls(
            name=str(name),
            vars=dict(vars_),
            tasks=tasks,
            modules=modules,
            includes=list(includes),
            presets=presets_config,
            defaults=list(defaults_),
        )
