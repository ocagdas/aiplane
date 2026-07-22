from __future__ import annotations

import subprocess

import pytest

from aiplane.docker_model_runner import DockerModelRunner


class StubCommandRunner:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **kwargs):
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.mark.parametrize(
    ("action", "model", "command"),
    [
        ("status", "all", ["docker", "model", "status", "--json"]),
        ("list-runtime-models", "all", ["docker", "model", "list", "--format", "json"]),
        ("inspect", "ai/model", ["docker", "model", "inspect", "ai/model"]),
        ("benchmark", "ai/model", ["docker", "model", "bench", "ai/model"]),
        ("install", "all", ["docker", "model", "install-runner"]),
        ("update", "all", ["docker", "model", "reinstall-runner"]),
        ("start", "all", ["docker", "model", "start-runner"]),
        ("stop", "all", ["docker", "model", "stop-runner"]),
        ("restart", "all", ["docker", "model", "restart-runner"]),
        ("pull", "ai/model", ["docker", "model", "pull", "ai/model"]),
        ("remove", "ai/model", ["docker", "model", "rm", "ai/model"]),
        ("clear", "all", ["docker", "model", "purge"]),
    ],
)
def test_commands_match_docker_model_runner_cli(action, model, command) -> None:
    assert DockerModelRunner.command(action, model=model) == command


def test_mutations_are_guarded_and_inventory_is_decoded() -> None:
    runner = StubCommandRunner()
    payload, code = DockerModelRunner(runner).run("pull", model="ai/model")
    assert code == 2
    assert payload["requires_yes"] is True
    assert runner.commands == []

    payload, code = DockerModelRunner(runner).run("pull", model="ai/model", yes=True)
    assert code == 0
    assert payload["executed"] is True

    inventory = StubCommandRunner(stdout='{"id":"ai/a"}\n{"id":"ai/b"}\n')
    payload, code = DockerModelRunner(inventory).run("list-runtime-models")
    assert code == 0
    assert payload["output"] == [{"id": "ai/a"}, {"id": "ai/b"}]
