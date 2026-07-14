from __future__ import annotations

from pathlib import Path

from aiplane.audit import AuditLogger
from aiplane.backends import AnthropicMessagesBackend, AzureOpenAIBackend, OllamaBackend, OpenAICompatibleBackend
from aiplane.benchmarks import BenchmarkRunner
from aiplane.config import load_profile
from aiplane.deploy import DeployManager
from aiplane.hardware import HardwareManager
from aiplane.integrations import IntegrationManager
from aiplane.machines import MachineManager
from aiplane.model_catalog import ModelCatalog
from aiplane.orchestrators import OrchestratorCatalog
from aiplane.providers import ProviderRegistry
from aiplane.remote import RemoteManager
from aiplane.runtime_catalog import RuntimeCatalog
from aiplane.stacks import StackManager
from aiplane.tools import ToolExecutor, ToolchainManager


from .boundary_fakes import FakeCommandRunner, FakeHttpTransport


def test_domain_managers_accept_explicit_boundaries() -> None:
    profile = load_profile("local-dev", Path.cwd())
    runner = FakeCommandRunner()
    transport = FakeHttpTransport()
    assert DeployManager(profile, command_runner=runner).command_runner is runner
    assert StackManager(profile, command_runner=runner).command_runner is runner
    assert IntegrationManager(profile, command_runner=runner).command_runner is runner
    assert RemoteManager(profile, command_runner=runner).command_runner is runner
    assert BenchmarkRunner(profile, command_runner=runner).command_runner is runner
    assert HardwareManager(profile, command_runner=runner).command_runner is runner
    catalog = ModelCatalog(profile, command_runner=runner, http_transport=transport)
    assert catalog.command_runner is runner
    assert catalog.http_transport is transport
    assert OrchestratorCatalog(profile, command_runner=runner).command_runner is runner
    assert ToolchainManager(profile, command_runner=runner).command_runner is runner
    assert ToolExecutor(profile, AuditLogger(profile), command_runner=runner).command_runner is runner
    machines = MachineManager(profile, command_runner=runner, http_transport=transport)
    assert machines.command_runner is runner
    assert machines.http_transport is transport
    assert ProviderRegistry(profile, http_transport=transport).http_transport is transport
    assert RuntimeCatalog(profile, http_transport=transport).http_transport is transport
    assert OllamaBackend(http_transport=transport).http_transport is transport
    assert OpenAICompatibleBackend("https://example.invalid/v1", http_transport=transport).http_transport is transport
    assert AnthropicMessagesBackend(http_transport=transport).http_transport is transport
    assert AzureOpenAIBackend("https://example.invalid", http_transport=transport).http_transport is transport


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
