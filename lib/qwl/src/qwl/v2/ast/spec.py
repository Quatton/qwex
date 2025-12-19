from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from qwl.ast.parser import Parser

YAML_PREFIX = "$"
PYTHON_PREFIX = "_"

def _default_hashfn(key: str) -> str:
    import xxhash
    
    return xxhash.xxh64_hexdigest(key)


@dataclass
class Module:
    _refs: dict[str, "RefSpec"]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Module":
        reserved, rest = {}, {}
        for key, value in d.items():
            if key.startswith(YAML_PREFIX):
                reserved[key[len(YAML_PREFIX) :]] = value
                pass
            else:
                rest[key] = value

        return cls(_refs={})

@dataclass
class RefProxy:
    _ctx: "Context"
    _key: str
    _value: str
    
    def __getattr__(self, name: str) -> Any:
        return getattr(self._ctx.hashmap[self._key], name)
    
@dataclass
class Context:
    modulemap: dict[str, "Module"] = field(default_factory=dict)
    hashmap: dict[str, "RefSpec"] = field(default_factory=dict)
    hashfn: Callable[[str], str] = _default_hashfn
    
    def get_module(self, 
                   parser: Parser,
                   source: str, 
                   overrides: Dict[str, Any]
                ) -> "Module":
        sourcehash = self.hashfn(source + str(overrides))
        
        

@dataclass
class RefSpec:
    _ctx: Context
    _key: str
    _refs: dict[str, "RefProxy"]
    _value: str

    @classmethod
    def from_dict(cls, ctx: Context, key: str, d: Dict[str, Any]) -> "RefSpec":
        reserved, refs = {}, {}
        for k, v in d.items():
            if k.startswith(YAML_PREFIX):
                reserved[k[len(YAML_PREFIX) :]] = v
            else:
                refs[k] = v

        _value = refs.get("", "")

        return cls(ctx, _key=key, _refs=refs, _value=_value)

    def __getitem__(self, key: str) -> "RefSpec":
        if key.startswith(PYTHON_PREFIX)