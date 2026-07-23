from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from aiplane.artifact_validation import validate_deployment_artifacts
from aiplane.cli_presenters import _environment_doctor_text
from aiplane.deploy import DeployManager
from aiplane.tools import ToolchainManager
from aiplane.vagrant_providers import (
    configured_local_vm_target,
    inspect_vagrant_provider,
    selected_vagrant_provider,
)

from .artifact_fixtures import copy_profile_targets, profile_with_local_vm_target
from .boundary_fakes import FakeCommandRunner
from .profile_fixtures import load_profile


def _locator(*available: str):
    paths = {name: f"/synthetic/bin/{name}" for name in available}
    return paths.get


def test_virtualbox_provider_requires_vagrant_and_a_working_capability_probe(tmp_path: Path) -> None:
    runner = FakeCommandRunner(stdout="7.1.0")
    status = inspect_vagrant_provider(
        "virtualbox",
        workspace=tmp_path,
        command_runner=runner,
        system="Linux",
        command_locator=_locator("vagrant", "VBoxManage"),
    )
    assert status["usable"] is True
    assert status["provider_command"] == "VBoxManage"
    assert status["plugin"] is None
    assert runner.commands == [["VBoxManage", "list", "hostinfo"]]


def test_virtualbox_kernel_module_warning_makes_provider_unusable(tmp_path: Path) -> None:
    runner = FakeCommandRunner(stderr="WARNING: The vboxdrv kernel module is not loaded")
    status = inspect_vagrant_provider(
        "virtualbox",
        workspace=tmp_path,
        command_runner=runner,
        system="Linux",
        command_locator=_locator("vagrant", "VBoxManage"),
    )
    assert status["usable"] is False
    assert status["capability_probe_ok"] is False
    assert "kernel module is not loaded" in status["reason"]


def test_libvirt_provider_requires_native_capability_and_vagrant_plugin(tmp_path: Path) -> None:
    def handler(command: list[str], _kwargs: dict[str, object]) -> subprocess.CompletedProcess[str]:
        stdout = "vagrant-libvirt (0.12.2, global)\n" if command[:3] == ["vagrant", "plugin", "list"] else "10.0.0\n"
        return subprocess.CompletedProcess(command, 0, stdout, "")

    present = inspect_vagrant_provider(
        "libvirt",
        workspace=tmp_path,
        command_runner=FakeCommandRunner(run_handler=handler),
        system="Linux",
        command_locator=_locator("vagrant", "virsh"),
    )
    assert present["usable"] is True
    assert present["plugin"] == "vagrant-libvirt"
    assert present["plugin_present"] is True

    absent = inspect_vagrant_provider(
        "libvirt",
        workspace=tmp_path,
        command_runner=FakeCommandRunner(stdout="No plugins installed."),
        system="Linux",
        command_locator=_locator("vagrant", "virsh"),
    )
    assert absent["usable"] is False
    assert "missing Vagrant plugin vagrant-libvirt" in absent["reason"]
    assert "vagrant plugin install vagrant-libvirt" in absent["remediation"]


def test_provider_platform_compatibility_is_explicit_without_running_probe(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    status = inspect_vagrant_provider(
        "hyperv",
        workspace=tmp_path,
        command_runner=runner,
        system="Linux",
        command_locator=_locator("vagrant", "powershell"),
    )
    assert status["usable"] is False
    assert status["platform_compatible"] is False
    assert "not supported on Linux" in status["reason"]
    assert runner.commands == []


@pytest.mark.parametrize("provider", ["virtualbox", "libvirt", "hyperv", "vmware_desktop"])
def test_local_vm_render_is_provider_specific_and_schema_safe(provider: str) -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, provider)
    payload = DeployManager(profile).render("local_dev_vm")
    assert payload["vm_provider"] == provider
    assert f'config.vm.provider "{provider}"' in payload["files"]["Vagrantfile"]
    assert payload["validation_commands"] == ["vagrant validate"]
    assert payload["next_commands"] == ["vagrant validate"]
    assert validate_deployment_artifacts(payload) is payload


def test_local_vm_render_rejects_unknown_provider_and_invalid_resources() -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "qemu")
    with pytest.raises(ValueError, match="vagrant provider must be one of"):
        DeployManager(profile).render("local_dev_vm")

    profile = profile_with_local_vm_target(source, "virtualbox")
    profile.targets["targets"]["local_dev_vm"]["memory_mb"] = 128
    with pytest.raises(ValueError, match="memory_mb must be at least 512"):
        DeployManager(profile).render("local_dev_vm")


def test_local_vm_workflow_requires_selected_provider_capability() -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "virtualbox")
    runner = FakeCommandRunner(stdout="Vagrant 2.4.9")

    def missing_provider(name: str) -> str | None:
        return "/synthetic/bin/vagrant" if name == "vagrant" else None

    with (
        patch("aiplane.tools.shutil.which", side_effect=missing_provider),
        patch("aiplane.vagrant_providers.shutil.which", side_effect=missing_provider),
    ):
        payload = ToolchainManager(profile, command_runner=runner, host_system="Linux").environment_doctor(
            workflow="local_vm", include_optional=False
        )
    readiness = payload["workflow_readiness"]
    assert readiness["readiness"] == "needs_setup"
    assert readiness["vm_provider_status"]["usable"] is False
    assert "install and enable the virtualbox provider executable" in readiness["next_actions"]
    assert "Vagrant provider virtualbox: unavailable" in _environment_doctor_text(payload)

    def usable_provider(name: str) -> str | None:
        if name in {"vagrant", "VBoxManage"}:
            return f"/synthetic/bin/{name}"
        return None

    with (
        patch("aiplane.tools.shutil.which", side_effect=usable_provider),
        patch("aiplane.vagrant_providers.shutil.which", side_effect=usable_provider),
    ):
        payload = ToolchainManager(profile, command_runner=runner, host_system="Linux").environment_doctor(
            workflow="local_vm", include_optional=False
        )
    assert payload["workflow_readiness"]["readiness"] == "ready"
    assert payload["workflow_readiness"]["vm_provider_status"]["usable"] is True


def test_vagrant_tool_plan_uses_configured_provider_and_reports_readiness() -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "libvirt")
    provider_status = {
        "name": "libvirt",
        "usable": False,
        "reason": "missing Vagrant plugin vagrant-libvirt",
    }
    manager = ToolchainManager(profile, command_runner=FakeCommandRunner())
    with patch.object(manager, "_tool_row", return_value={"category": "vm", "provider_status": provider_status}):
        payload = manager.plan("vagrant")
    assert payload["provider_status"] == provider_status
    assert payload["commands"][0] == "vagrant validate"
    assert payload["commands"][1] == "vagrant up --provider libvirt"


def test_vagrant_tool_export_uses_configured_target_provider() -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "libvirt")
    payload = ToolchainManager(profile, command_runner=FakeCommandRunner()).export("vagrant")
    assert payload["provider"] == "libvirt"
    assert payload["filename"] == "Vagrantfile"
    assert 'config.vm.provider "libvirt"' in payload["content"]
    assert 'config.vm.provider "virtualbox"' not in payload["content"]


def test_workflow_plan_reports_provider_status_and_remediation() -> None:
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "libvirt")
    status = {
        "name": "libvirt",
        "usable": False,
        "reason": "missing Vagrant plugin vagrant-libvirt",
        "remediation": ["vagrant plugin install vagrant-libvirt"],
    }
    with patch("aiplane.deploy.inspect_vagrant_provider", return_value=status):
        plan = DeployManager(profile).workflow_plan("local_dev_vm")
    assert plan["vm_provider"] == "libvirt"
    assert plan["vm_provider_status"] == status
    assert "libvirt" in plan["recommended_tools"]


def test_multiple_local_vm_targets_require_an_explicit_default() -> None:
    source = load_profile("local-dev", Path.cwd())
    targets = copy_profile_targets(source)
    targets.pop("local_vm_default", None)
    targets["targets"]["secondary_vm"] = {
        "type": "local_vm",
        "provider": "libvirt",
    }
    with pytest.raises(ValueError, match="multiple local VM targets.*local_vm_default"):
        configured_local_vm_target(targets)

    targets["local_vm_default"] = "secondary_vm"
    name, target = configured_local_vm_target(targets)
    assert name == "secondary_vm"
    assert target["provider"] == "libvirt"


def test_provider_aliases_are_normalized() -> None:
    assert selected_vagrant_provider({"provider": "hyper-v"}) == "hyperv"
    assert selected_vagrant_provider({"provider": "vmware"}) == "vmware_desktop"
