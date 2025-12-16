from collections.abc import Callable
from typing import Any


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


class Parser:
    def __init__(self, file_loader: Callable[[str], str] = read_file):
        self._file_loader = file_loader

    def parse_file(self, filepath: str):
        source = self._file_loader(filepath)
        return self.parse(source)

    def parse(self, source: str):
        data = parse_yaml(source)

        from qwl.ast.spec import Module

        if not isinstance(data, dict):
            raise ValueError("Parsed YAML must be a mapping at the top level")

        return Module.from_dict(data)
