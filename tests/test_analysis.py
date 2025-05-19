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
    expected_src = str((tmp_path / "foo").resolve())
    assert result == {
        "prepare": {
            "commands": ["a", "b"],
            "copy_files": [{"src": expected_src, "dest": "bar"}],
        }
    }


def test_copy_files_paths_resolved(tmp_path: Path) -> None:
    src_file = tmp_path / "src.txt"
    src_file.write_text("data")

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        """base_image: test
prepare:
  copy_files:
    - src: src.txt
      dest: /root/src.txt
"""
    )

    result = load_config(cfg)
    assert Path(result["prepare"]["copy_files"][0]["src"]) == src_file.resolve()


def test_copy_files_paths_resolved_with_extends(tmp_path: Path) -> None:
    parent_dir = tmp_path / "parent"
    parent_dir.mkdir()
    parent_file = parent_dir / "parent.yaml"
    parent_src = parent_dir / "p.txt"
    parent_src.write_text("p")
    parent_file.write_text(
        """prepare:
  copy_files:
    - src: p.txt
      dest: /root/p.txt
"""
    )

    child_dir = tmp_path / "child"
    child_dir.mkdir()
    child_file = child_dir / "child.yaml"
    child_src = child_dir / "c.txt"
    child_src.write_text("c")
    child_file.write_text(
        f"extends: ../parent/parent.yaml\nprepare:\n  copy_files:\n    - src: c.txt\n      dest: /root/c.txt\n"
    )

    result = load_config(child_file)
    paths = [Path(e["src"]) for e in result["prepare"]["copy_files"]]
    assert paths == [parent_src.resolve(), child_src.resolve()]

