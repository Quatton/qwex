# Qwex CLI

Command-line interface for Qwex Protocol.

## Installation

```bash
pip install qwexcli
```

## Usage

Currently the CLI provides a small set of project commands. The primary
supported command at the moment is:

- `qwex init` — initialize a project in the current repository (creates `.qwex/config.yaml`).

More commands will be added over time. If you need a feature that's not
documented here, please open an issue or a PR.

## How it works (current)

- `qwex init` creates a `.qwex` directory and a `config.yaml` file containing the project name.

## License

MIT
