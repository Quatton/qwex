from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleRef:
    """Reference to an external module to import."""

    name: str
    source: str


@dataclass
class Module:
    name: str
    vars: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, "Task"] = field(default_factory=dict)
    modules: Dict[str, ModuleRef] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        if not isinstance(d, dict):
            raise TypeError("Module.from_dict expects a mapping")

        name = d.get("name")
        if not name:
            raise ValueError("Missing required 'name' in Module dict")

        vars_ = d.get("vars") or {}
        if not isinstance(vars_, dict):
            raise TypeError("Module 'vars' must be a mapping")

        tasks_ = d.get("tasks") or {}
        if not isinstance(tasks_, dict):
            raise TypeError("Module 'tasks' must be a mapping")

        modules_ = d.get("modules") or {}
        if not isinstance(modules_, dict):
            raise TypeError("Module 'modules' must be a mapping")

        tasks: Dict[str, Task] = {}
        for tname, td in tasks_.items():
            tasks[tname] = Task.from_dict(tname, td)

        modules: Dict[str, ModuleRef] = {}
        for mname, md in modules_.items():
            if isinstance(md, dict) and "source" in md:
                modules[mname] = ModuleRef(name=mname, source=md["source"])
            else:
                raise ValueError(f"Module '{mname}' must have 'source' field")

        return cls(name=str(name), vars=dict(vars_), tasks=tasks, modules=modules)


@dataclass
class Task:
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
