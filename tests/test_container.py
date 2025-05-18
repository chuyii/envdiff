import subprocess

import pytest

from envdiff.container import ContainerManager, DEFAULT_CONTAINER_TOOL


@pytest.fixture
def cm():
    # Avoid container interactions by not creating or starting any container.
    return ContainerManager(DEFAULT_CONTAINER_TOOL)


def test_run_command_failure(cm):
    with pytest.raises(subprocess.CalledProcessError):
        cm._run_command(["false"])


def test_run_command_success(cm):
    result = cm._run_command(["echo", "ok"])
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"

