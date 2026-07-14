from __future__ import annotations

from pathlib import Path

import pytest

from aiplane.config import load_profile
from aiplane.hardware import HardwareManager
from aiplane.platform_support import HostPlatform, detect_host_platform


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


def test_hardware_discovery_skips_linux_commands_on_non_linux(monkeypatch, tmp_path: Path) -> None:
    profile = load_profile("local-dev", tmp_path)
    host = HostPlatform("Darwin", None, (), "arm64")

    def forbidden_which(command: str):
        raise AssertionError(f"must not probe {command} on macOS")

    monkeypatch.setattr("aiplane.hardware.shutil.which", forbidden_which)
    result = HardwareManager(profile, host_platform=host).discover()

    assert result["platform_support"]["system"] == "Darwin"
    assert result["memory_gb"] is None
    assert result["gpus"] == []
    assert any("skipped" in note for note in result["notes"])


def test_unsupported_payload_distinguishes_platform_from_missing_tool() -> None:
    host = HostPlatform("Linux", "fedora", ("rhel",), "x86_64")
    payload = host.unsupported("runtime_helper_install", ["Ubuntu Linux", "Debian Linux"], "unsupported distro")
    assert payload["name"] == "unsupported_platform"
    assert payload["platform"]["distribution"] == "fedora"
    assert "tool" not in payload
