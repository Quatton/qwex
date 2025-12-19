import re
from typing import Any, Callable


class Parser:
    _file_loader: Callable[[str], str]

    def __init__(self, file_loader: Callable[[str], str] | None = None):
        self._file_loader = file_loader or read_file

    def parse_file(self, filepath: str):
        source = self._file_loader(filepath)
        if re.match(r"\.y(a)?ml$", filepath):
            return self.parse_yaml(source)
        else:
            # just a YAML parser for now
            return self.parse_yaml(source)

    def parse_yaml(self, source: str):
        data = parse_yaml(source)

        from qwl.v2.ast.spec import Module

        if not isinstance(data, dict):
            raise ValueError("Parsed YAML must be a mapping at the top level")

        return Module.from_dict(data)


class Pipeline:
    """
    RefHash {
      hash: str
    }

    Context {
      hashmap: Dict[str, RefSpec],
    }

    ModuleTree {
      refs: Dict[str, RefHash]
    }

    RefSpec {
      dependencies: List[RefHash],
      value: str,
      children: Dict[str, RefHash]
    }

    First, the parser will parse the YAML into a dict.


    Then, the resolver will recursively resolve each ref in the stack:

    {
      "props": {
        "things": 3,
        "reference_other": "{{ commands.greet.run }}",
      },
      "modules": {
        "log": {
          "source": "std/log",
          "props": {
            "level": "debug"
        }
      },
      "tasks": {
        "greet": {
          "run": "echo 'Hello, World!'"
        "greetwithprops": {
          "props": {
            "times": 5
          },
          "run": "for i in $(seq 1 {{ props.times }}); do echo 'Hello!'; done"
        },
        "loginline": {
          "uses": "log:info",
          "props": {
            "level": "info"
          }
        },
      }
    },

    here's how the resolver works:

    waterfall hash

    "each module can instantiate another module with different props"
    modulesourcehash > moduleoverrideshash > tasksourcehash > taskoverrideshash

    cache:
    - absolute path aggregator: absolute path -> hash(source_str)
      - on-cache-empty: read file, hash contents, store in module cache
    - module source cache: hash(source_str) -> sourcehash
    - overrides cache: hash(overrides dict str) -> overrides dict
    - module backtracker: overrideshash + sourcehash -> modulehash
    - alias resolver: modulealias + caller absolute path -> (through sourcedict) -> module source absolute path  -> can reuse [absolute path aggregator] to get sourcehash -> get  source and manually overrides
    - task cache: hash(hash(modulehash) + hash(overrides)) -> task
    - task backtracker: taskhash -> modulehash


    """

    parser: "Parser"

    pass


def read_file(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            return file.read()
    except OSError as exc:
        raise FileNotFoundError(f"Could not read file: {filepath}") from exc


def parse_yaml(source: str) -> Any:
    import yaml
    from yaml import YAMLError

    if not isinstance(source, str):
        raise TypeError("`source` must be a string containing YAML")

    try:
        data = yaml.safe_load(source)
    except YAMLError as exc:
        raise ValueError("Failed to parse YAML") from exc

    return data
