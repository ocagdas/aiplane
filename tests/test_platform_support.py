from __future__ import annotations

from pathlib import Path
import json

import pytest

from aiplane.cli import main as cli_main
from aiplane.config import load_profile
from aiplane.hardware import HardwareManager
from aiplane.platform_support import HostPlatform, detect_host_platform
from aiplane.remote import RemoteManager

from .boundary_fakes import FakeCommandRunner


@pytest.mark.parametrize(
    ("release", "expected"),
    [
        ("ID=ubuntu\nID_LIKE=debian\n", ("ubuntu", True)),
        ("ID=debian\n", ("debian", True)),
        ("ID=fedora\nID_LIKE=rhel\n", ("fedora", False)),
    ],
)
def test_linux_distribution_capabilities_are_data_driven(release: str, expected: tuple[str, bool]) -> None:
    host = detect_host_platform(system="Linux", machine="x86_64", os_release_text=release, proc_version_text="Linux")
    assert host.distribution == expected[0]
    assert host.runtime_helper_supported is expected[1]
    assert host.linux_hardware_probes_supported


def test_wsl_is_explicitly_inspection_only_for_runtime_helpers() -> None:
    host = detect_host_platform(
        system="Linux",
        machine="x86_64",
        os_release_text="ID=ubuntu\nWSL_DISTRO_NAME=Ubuntu\n",
        proc_version_text="Linux microsoft-standard-WSL2",
    )
    assert host.wsl
    assert host.linux_hardware_probes_supported
    assert not host.runtime_helper_supported


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_non_linux_platforms_do_not_claim_linux_capabilities(system: str) -> None:
    host = detect_host_platform(system=system, machine="arm64", os_release_text="", proc_version_text="")
    assert not host.linux
    assert not host.runtime_helper_supported
    assert not host.linux_hardware_probes_supported


@pytest.mark.parametrize("system", ["Darwin", "Windows"])
def test_hardware_discovery_uses_platform_specific_probes(tmp_path: Path, system: str) -> None:
    profile = load_profile("local-dev", tmp_path)
    host = HostPlatform(system, None, (), "arm64")

    runner = FakeCommandRunner(returncode=1)
    result = HardwareManager(profile, command_runner=runner, host_platform=host).discover()

    assert result["platform_support"]["system"] == system
    assert result["memory_gb"] is None
    assert result["gpus"] == []
    assert any("No supported accelerator" in note for note in result["notes"])
    if system == "Darwin":
        assert [command[:2] for command in runner.commands] == [
            ["sysctl", "-n"],
            ["system_profiler", "SPDisplaysDataType"],
        ]
    else:
        assert len(runner.commands) == 1
        assert runner.commands[0][:3] == ["powershell", "-NoProfile", "-NonInteractive"]


def test_unsupported_payload_distinguishes_platform_from_missing_tool() -> None:
    host = HostPlatform("Linux", "fedora", ("rhel",), "x86_64")
    payload = host.unsupported("runtime_helper_install", ["Ubuntu Linux", "Debian Linux"], "unsupported distro")
    assert payload["name"] == "unsupported_platform"
    assert payload["platform"]["distribution"] == "fedora"
    assert "tool" not in payload


@pytest.mark.parametrize(
    "host",
    [
        HostPlatform("Darwin", None, (), "arm64"),
        HostPlatform("Windows", None, (), "AMD64"),
        HostPlatform("Linux", "fedora", ("rhel",), "x86_64"),
        HostPlatform("Linux", "ubuntu", ("debian",), "x86_64", wsl=True),
    ],
)
def test_unsupported_runtime_mutation_never_calls_helper(monkeypatch, capsys, host: HostPlatform) -> None:
    monkeypatch.setattr("aiplane.cli_runtimes.detect_host_platform", lambda: host)

    def forbidden_helper(*args, **kwargs):
        raise AssertionError("unsupported platform must fail before helper execution")

    monkeypatch.setattr("aiplane.cli_runtimes._run_provider_helper", forbidden_helper)
    assert cli_main(["runtimes", "install", "ollama", "--dry-run"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "unsupported_platform"
    assert payload["platform"]["system"] == host.system


def test_windows_tunnel_lifecycle_fails_before_process_or_state_mutation(tmp_path: Path) -> None:
    profile = load_profile("local-dev", tmp_path)

    class ForbiddenRunner:
        def run(self, *args, **kwargs):
            raise AssertionError("unsupported lifecycle must not inspect processes")

        def popen(self, *args, **kwargs):
            raise AssertionError("unsupported lifecycle must not spawn ssh")

    manager = RemoteManager(
        profile,
        command_runner=ForbiddenRunner(),
        host_platform=HostPlatform("Windows", None, (), "AMD64"),
    )
    assert manager.tunnel_plan("gpu_workstation_ssh")["type"] == "ssh_tunnel"
    for action in ("status", "start", "stop"):
        method = getattr(manager, f"tunnel_{action}")
        payload = method("gpu_workstation_ssh", yes=True) if action != "status" else method("gpu_workstation_ssh")
        assert payload["name"] == "unsupported_platform"
        assert payload["operation"] == "ssh_tunnel_lifecycle"
        assert payload["action"] == action
    assert not (tmp_path / ".aiplane").exists()


def test_remote_lifecycle_help_states_windows_boundary(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        cli_main(["remote", "tunnel", "start", "--help"])
    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "Linux/macOS" in output
    assert "On Windows use tunnel plan" in output
