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


def test_load_config_with_extends(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("a: 1\nlist:\n  - 1\n")

    child = tmp_path / "child.yaml"
    child.write_text("extends: [base.yaml]\nlist:\n  - 2\nb: 3\n")

    result = load_config(child)

    assert result == {"a": 1, "list": [1, 2], "b": 3}


def test_load_config_with_nested_dicts(tmp_path):
    parent = tmp_path / "parent.yaml"
    parent.write_text("prepare:\n  commands:\n    - a\n")

    child = tmp_path / "child.yaml"
    child.write_text(
        "extends: [parent.yaml]\nprepare:\n  commands:\n    - b\n  copy_files:\n    - src: foo\n      dest: bar\n"
    )

    result = load_config(child)

    assert result == {
        "prepare": {
            "commands": ["a", "b"],
            "copy_files": [{"src": "foo", "dest": "bar"}],
        }
    }

