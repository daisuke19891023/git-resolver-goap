from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from goapgit.core.models import Config
from goapgit.io.config import load_config


SAMPLE_TOML = """
[goal]
mode = "rebase_to_upstream"
tests_must_pass = true
push_with_lease = true

[strategy]
conflict_style = "zdiff3"
enable_rerere = true
rules = [
  { pattern = "**/*.lock", resolution = "theirs" }
]

[safety]
dry_run = false
allow_force_push = false
max_test_runtime_sec = 120
"""


def test_load_config_from_path(tmp_path: pathlib.Path) -> None:
    """Loading from disk should produce a validated Config instance."""
    config_path = pathlib.Path(tmp_path / "goapgit.toml")
    config_path.write_text(SAMPLE_TOML)

    config = load_config(path=config_path)

    assert isinstance(config, Config)
    assert config.goal.push_with_lease is True
    assert config.strategy_rules[0].pattern == "**/*.lock"
    assert config.dry_run is False


def test_load_config_with_overrides(tmp_path: pathlib.Path) -> None:
    """Overrides should merge into the loaded configuration."""
    config_path = pathlib.Path(tmp_path / "goapgit.toml")
    config_path.write_text(SAMPLE_TOML)

    config = load_config(path=config_path, overrides={"safety": {"dry_run": True}})

    assert config.dry_run is True


def test_invalid_config_raises_validation_error(tmp_path: pathlib.Path) -> None:
    """Invalid settings should surface as ValidationError."""
    invalid_toml = SAMPLE_TOML.replace("dry_run = false", 'dry_run = "nope"')
    config_path = pathlib.Path(tmp_path / "goapgit.toml")
    config_path.write_text(invalid_toml)

    with pytest.raises(ValidationError):
        load_config(path=config_path)


def test_missing_config_file_raises(tmp_path: pathlib.Path) -> None:
    """Referencing a missing file should raise FileNotFoundError."""
    missing_path = pathlib.Path(tmp_path / "missing.toml")
    with pytest.raises(FileNotFoundError):
        load_config(path=missing_path)
