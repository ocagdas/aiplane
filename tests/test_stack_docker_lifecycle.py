from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import patch

from aiplane.machines import MachineManager
from aiplane.stacks import StackManager
from tests.profile_fixtures import _isolated_test_profile


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command, **kwargs):
        self.calls.append(list(command))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


@contextmanager
def _docker_stack(tmp_path: Path, runner: RecordingRunner) -> Iterator[StackManager]:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        models = copy.deepcopy(profile.models)
        models["models"]["fixture-dmr"] = {
            "provider": "docker_model",
            "model": "ai/example-chat:Q4_K_M",
            "supported_runtimes": ["docker_model_runner"],
            "roles": ["chat", "analysis"],
            "local": True,
            "enabled": True,
            "min_ram_gb": 4,
            "min_vram_gb": 0,
        }
        profile = replace(profile, models=models)
        manager = MachineManager(profile)
        exported = manager.export_machine("local-docker-box")
        machine_path = profile.root / "local-docker-box.json"
        machine_path.write_text(json.dumps(exported), encoding="utf-8")
        manager.import_file(machine_path)
        stacks = StackManager(profile, command_runner=runner)
        stacks.setup(
            "docker-stack",
            orchestrator=None,
            runtime="docker_model_runner",
            model="fixture-dmr",
            machine="local-docker-box",
            access="same_host",
        )
        yield stacks


def test_docker_stack_uses_native_model_commands_and_exact_endpoint(tmp_path: Path) -> None:
    runner = RecordingRunner()
    with _docker_stack(tmp_path, runner) as stacks:
        with patch(
            "aiplane.runtime_catalog.RuntimeCatalog.runtime_available",
            return_value={"name": "docker_model_runner", "available": False},
        ):
            plan = stacks.plan("docker-stack")
            preview = stacks.prepare("docker-stack", dry_run=True)
            status = stacks.status("docker-stack")
        assert plan["endpoint"] == "http://localhost:12434/engines/v1"
        assert [step["command"] for step in plan["steps"] if step.get("adapter") == "docker_model_runner"] == [
            ["docker", "model", "install-runner"],
            ["docker", "model", "pull", "ai/example-chat:Q4_K_M"],
            ["docker", "model", "start-runner"],
        ]
        assert [row["command"] for row in preview["commands"]] == [
            ["docker", "model", "install-runner"],
            ["docker", "model", "pull", "ai/example-chat:Q4_K_M"],
        ]
        assert status["runtime_substrate"] == "docker"
        assert status["runtime_evidence"]["launch_manifest"]["runtime"]["name"] == "docker_model_runner"
        assert runner.calls == []


def test_stack_lifecycle_requires_confirmation_before_any_command(tmp_path: Path) -> None:
    runner = RecordingRunner()
    with _docker_stack(tmp_path, runner) as stacks:
        with patch(
            "aiplane.runtime_catalog.RuntimeCatalog.runtime_available",
            return_value={"name": "docker_model_runner", "available": False},
        ):
            blocked = stacks.start("docker-stack")
            executed = stacks.start("docker-stack", yes=True)
        assert blocked["status"] == "confirmation_required"
        assert blocked["requires_yes"] is True
        assert executed["outcome"] == "completed"
        assert runner.calls == [["docker", "model", "start-runner"]]
