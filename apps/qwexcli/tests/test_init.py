import yaml

from qwexcli.lib.project import (
    create_config_file,
    check_already_initialized,
    scaffold,
    AlreadyInitializedError,
)
from qwexcli.lib.config import load_config


def test_create_config_file_writes_yaml(tmp_path):
    cwd = tmp_path
    cfg_path = cwd / ".qwex" / "config.yaml"

    out = create_config_file(config_path=cfg_path)
    assert out == cfg_path
    assert cfg_path.exists()

    with open(cfg_path, "r") as f:
        data = yaml.safe_load(f)

    assert data is not None
    assert data.get("name") == cwd.name
    # Defaults and runners should not be written by the scaffold by default.
    assert "defaults" not in data
    assert "runners" not in data


def test_check_already_initialized_raises(tmp_path):
    cwd = tmp_path
    cfg_path = cwd / ".qwex" / "config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("name: existing\n")

    try:
        check_already_initialized(cfg_path)
        raise AssertionError("Expected AlreadyInitializedError")
    except AlreadyInitializedError:
        pass


def test_check_already_initialized_passes_when_not_initialized(tmp_path):
    # Should not raise when config doesn't exist
    cfg_path = tmp_path / ".qwex" / "config.yaml"
    check_already_initialized(cfg_path)


def test_scaffold_returns_path(tmp_path):
    cwd = tmp_path
    cfg_path = cwd / ".qwex" / "config.yaml"
    out = scaffold(config_path=cfg_path, name="myproj")
    assert out == cfg_path

    with open(out, "r") as f:
        data = yaml.safe_load(f)
    assert data.get("name") == "myproj"
    # scaffold should ensure .gitignore exists
    gitignore = cfg_path.parent / ".gitignore"
    assert gitignore.exists()
    assert "internal/" in gitignore.read_text()


def test_config_roundtrip_preserves_name(tmp_path):
    """Save then load config; verify name is preserved."""
    cwd = tmp_path
    cfg_path = create_config_file(
        config_path=cwd / ".qwex" / "config.yaml", name="roundtrip-test"
    )

    loaded = load_config(cfg_path)
    assert loaded.name == "roundtrip-test"
    # Defaults are filled in on load
    assert loaded.version == 1
    # New config schema uses defaults and runners but no default 'base' runner
    assert loaded.defaults is None
    assert loaded.runners is None


def test_config_exclude_unset_only_writes_explicit_fields(tmp_path):
    """Verify that only explicitly set fields are written to YAML."""
    cwd = tmp_path
    cfg_path = create_config_file(
        config_path=cwd / ".qwex" / "config.yaml", name="explicit-only"
    )

    with open(cfg_path, "r") as f:
        data = yaml.safe_load(f)

    # 'name', 'defaults', and 'runners' were provided explicitly by scaffold
    assert "name" in data
    # 'name' was provided explicitly by scaffold; defaults/runners should be
    # omitted.
    assert "defaults" not in data
    assert "runners" not in data
    # 'version' is a default and not explicitly written
    assert "version" not in data
