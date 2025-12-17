from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleRef:
    """Reference to an external module to import."""

    name: str
    source: str


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
        vars_ = d.get("vars") or {}
        env_ = d.get("env") or {}
        uses = d.get("uses")
        with_ = d.get("with") or []

        if run is None:
            run_val = None
        else:
            run_val = str(run)

        # accept either a mapping or a list (some task types use a list of steps)
        if not isinstance(vars_, (dict, list)):
            raise TypeError(f"Task '{name}' 'vars' must be a mapping or list")
        if not isinstance(env_, dict):
            raise TypeError(f"Task '{name}' 'env' must be a mapping")

        return cls(
            name=name,
            run=run_val,
            vars=dict(vars_) if isinstance(vars_, dict) else {},
            env=dict(env_),
            uses=uses,
            with_=with_,
        )


@dataclass
class Preset:
    """A preset is like a partial module - can define vars, tasks, includes, and modules.
    
    When activated, its content is merged into the root module.
    Presets are applied in order, with later presets overriding earlier ones.
    The root module's own definitions have highest priority.
    """

    name: str
    vars: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, Task] = field(default_factory=dict)
    modules: Dict[str, ModuleRef] = field(default_factory=dict)
    includes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, d: dict) -> "Preset":
        if not isinstance(d, dict):
            raise TypeError(f"Preset '{name}' must be a mapping")

        vars_ = d.get("vars") or {}
        includes_ = d.get("includes") or []
        tasks_ = d.get("tasks") or {}
        modules_ = d.get("modules") or {}

        if not isinstance(vars_, dict):
            raise TypeError(f"Preset '{name}' 'vars' must be a mapping")
        if not isinstance(includes_, list):
            raise TypeError(f"Preset '{name}' 'includes' must be a list")
        if not isinstance(tasks_, dict):
            raise TypeError(f"Preset '{name}' 'tasks' must be a mapping")
        if not isinstance(modules_, dict):
            raise TypeError(f"Preset '{name}' 'modules' must be a mapping")

        # Parse tasks
        tasks: Dict[str, Task] = {}
        for tname, td in tasks_.items():
            tasks[tname] = Task.from_dict(tname, td)

        # Parse modules
        modules: Dict[str, ModuleRef] = {}
        for mname, md in modules_.items():
            if isinstance(md, dict) and "source" in md:
                modules[mname] = ModuleRef(name=mname, source=md["source"])
            else:
                raise ValueError(f"Preset '{name}' module '{mname}' must have 'source' field")

        return cls(
            name=name,
            vars=dict(vars_),
            tasks=tasks,
            modules=modules,
            includes=list(includes_),
        )


@dataclass
class Module:
    """A module is the root unit containing tasks, vars, imports, and presets."""

    name: str
    vars: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, Task] = field(default_factory=dict)
    modules: Dict[str, ModuleRef] = field(default_factory=dict)
    includes: List[str] = field(default_factory=list)
    presets: Dict[str, Preset] = field(default_factory=dict)
    defaults: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        if not isinstance(d, dict):
            raise TypeError("Module.from_dict expects a mapping")

        name = d.get("name", "root")

        vars_ = d.get("vars") or {}
        if not isinstance(vars_, dict):
            raise TypeError("Module 'vars' must be a mapping")

        tasks_ = d.get("tasks") or {}
        if not isinstance(tasks_, dict):
            raise TypeError("Module 'tasks' must be a mapping")

        modules_ = d.get("modules") or {}
        if not isinstance(modules_, dict):
            raise TypeError("Module 'modules' must be a mapping")

        includes_ = d.get("includes") or []
        if not isinstance(includes_, list):
            raise TypeError("Module 'includes' must be a list")

        presets_ = d.get("presets") or {}
        if not isinstance(presets_, dict):
            raise TypeError("Module 'presets' must be a mapping")

        defaults_ = d.get("defaults") or []
        if not isinstance(defaults_, list):
            raise TypeError("Module 'defaults' must be a list")

        tasks: Dict[str, Task] = {}
        for tname, td in tasks_.items():
            tasks[tname] = Task.from_dict(tname, td)

        modules: Dict[str, ModuleRef] = {}
        for mname, md in modules_.items():
            if isinstance(md, dict) and "source" in md:
                modules[mname] = ModuleRef(name=mname, source=md["source"])
            else:
                raise ValueError(f"Module '{mname}' must have 'source' field")

        presets: Dict[str, Preset] = {}
        for pname, pd in presets_.items():
            presets[pname] = Preset.from_dict(pname, pd)

        return cls(
            name=str(name),
            vars=dict(vars_),
            tasks=tasks,
            modules=modules,
            includes=list(includes_),
            presets=presets,
            defaults=list(defaults_),
        )
