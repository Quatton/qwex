from __future__ import annotations

from typing import Dict, List, Optional, Union

import msgspec


class TaskBase(msgspec.Struct):
    pass


class TaskCmd(TaskBase):
    _cmd: str = msgspec.field(name="cmd")
    desc: Optional[str] = None

    @property
    def cmd(self) -> List[str]:
        return [self._cmd]


class TaskCmds(TaskBase):
    _cmd: List[str] = msgspec.field(name="cmd")
    desc: Optional[str] = None

    @property
    def cmd(self) -> List[str]:
        return self._cmd


class Config(msgspec.Struct):
    """Top-level configuration containing vars and tasks."""

    vars: Dict[str, str]
    tasks: Dict[str, Union[TaskCmd, TaskCmds]]
