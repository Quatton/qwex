from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Module:
    name: str
    vars: Dict[str, Any] = field(default_factory=dict)
    tasks: Dict[str, "Task"] = field(default_factory=dict)

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

        tasks: Dict[str, Task] = {}
        for tname, td in tasks_.items():
            tasks[tname] = Task.from_dict(tname, td)

        return cls(name=str(name), vars=dict(vars_), tasks=tasks)


@dataclass
class Task:
    name: str
    run: Optional[str] = None

    @classmethod
    def from_dict(cls, name: str, d: Any) -> "Task":
        if isinstance(d, str):
            return cls(name=name, run=d)

        if not isinstance(d, dict):
            raise TypeError(f"Task '{name}' must be a mapping or string")

        run = d.get("run")

        if run is None:
            run_val = None
        else:
            run_val = str(run)

        return cls(name=name, run=run_val)
