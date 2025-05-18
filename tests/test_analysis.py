from pathlib import Path

import pytest

from envdiff.analysis import load_config


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config(Path("nonexistent_file.yaml"))


def test_load_config_valid_yaml(tmp_path):
    tmp_file = tmp_path / "valid.yaml"
    tmp_file.write_text("key: value\n")

    data = load_config(tmp_file)

    assert data == {"key": "value"}

