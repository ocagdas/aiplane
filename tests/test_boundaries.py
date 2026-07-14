from __future__ import annotations

import json
import subprocess
from pathlib import Path

from aiplane.config import load_profile
from aiplane.deploy import DeployManager
from aiplane.integrations import IntegrationManager
from aiplane.machines import MachineManager
from aiplane.providers import ProviderRegistry
from aiplane.stacks import StackManager


class FakeCommandRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **kwargs):
        self.commands.append(command)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    def popen(self, command: list[str], **kwargs):
        raise AssertionError("popen was not expected")


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps({"data": [{"id": "synthetic-model"}]}).encode()


class FakeHttpTransport:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, *, timeout: float):
        self.requests.append((request, timeout))
        return FakeResponse()


def test_domain_managers_accept_explicit_boundaries() -> None:
    profile = load_profile("local-dev", Path.cwd())
    runner = FakeCommandRunner()
    transport = FakeHttpTransport()
    assert DeployManager(profile, command_runner=runner).command_runner is runner
    assert StackManager(profile, command_runner=runner).command_runner is runner
    assert IntegrationManager(profile, command_runner=runner).command_runner is runner
    machines = MachineManager(profile, command_runner=runner, http_transport=transport)
    assert machines.command_runner is runner
    assert machines.http_transport is transport
    assert ProviderRegistry(profile, http_transport=transport).http_transport is transport


def test_deploy_apply_uses_injected_runner() -> None:
    profile = load_profile("local-dev", Path.cwd())
    runner = FakeCommandRunner()
    result = DeployManager(profile, command_runner=runner).apply("azure_gpu_vm", yes=True)
    assert result["results"]
    assert runner.commands == [row["command"] for row in result["results"]]


def test_provider_http_uses_injected_transport() -> None:
    profile = load_profile("local-dev", Path.cwd())
    transport = FakeHttpTransport()
    payload = ProviderRegistry(profile, http_transport=transport)._json_get("https://example.invalid/v1/models")
    assert payload["data"][0]["id"] == "synthetic-model"
    assert len(transport.requests) == 1
