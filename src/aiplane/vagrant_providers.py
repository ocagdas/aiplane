"""Vagrant provider selection and non-mutating host capability checks."""

from __future__ import annotations

import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner


@dataclass(frozen=True)
class VagrantProviderSpec:
    name: str
    vagrant_name: str
    systems: tuple[str, ...]
    executables: tuple[str, ...]
    plugin: str | None = None
    probe_args: tuple[str, ...] = ("--version",)
    failure_markers: tuple[str, ...] = ()


VAGRANT_PROVIDERS = {
    "virtualbox": VagrantProviderSpec(
        "virtualbox",
        "virtualbox",
        ("Darwin", "Linux", "Windows"),
        ("VBoxManage", "vboxmanage"),
        probe_args=("list", "hostinfo"),
        failure_markers=("kernel module is not loaded", "will not be able to start vms"),
    ),
    "libvirt": VagrantProviderSpec(
        "libvirt",
        "libvirt",
        ("Linux",),
        ("virsh",),
        plugin="vagrant-libvirt",
    ),
    "hyperv": VagrantProviderSpec(
        "hyperv",
        "hyperv",
        ("Windows",),
        ("powershell", "pwsh"),
        probe_args=("-NoProfile", "-Command", "Get-Command Get-VMHost -ErrorAction Stop | Out-Null"),
    ),
    "vmware_desktop": VagrantProviderSpec(
        "vmware_desktop",
        "vmware_desktop",
        ("Darwin", "Linux", "Windows"),
        ("vmrun",),
        plugin="vagrant-vmware-desktop",
        probe_args=(),
    ),
}

_PROVIDER_ALIASES = {
    "hyper-v": "hyperv",
    "vmware": "vmware_desktop",
    "vmware-desktop": "vmware_desktop",
}


def selected_vagrant_provider(target: dict[str, Any]) -> str:
    value = str(target.get("vagrant_provider") or target.get("provider") or "virtualbox").strip().lower()
    selected = _PROVIDER_ALIASES.get(value, value)
    if selected not in VAGRANT_PROVIDERS:
        choices = ", ".join(VAGRANT_PROVIDERS)
        raise ValueError(f"target vagrant provider must be one of: {choices}")
    return selected


def inspect_vagrant_provider(
    provider: str,
    *,
    workspace: Path,
    command_runner: CommandRunner | None = None,
    system: str | None = None,
    command_locator: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    try:
        spec = VAGRANT_PROVIDERS[provider]
    except KeyError as exc:
        choices = ", ".join(VAGRANT_PROVIDERS)
        raise ValueError(f"unknown Vagrant provider {provider!r}; available: {choices}") from exc

    host_system = system or platform.system()
    locator = command_locator or shutil.which
    platform_compatible = host_system in spec.systems
    vagrant_path = locator("vagrant")
    executable_name, executable_path = _first_executable(spec.executables, locator)
    runner = command_runner or SubprocessCommandRunner()
    probe_ok = False
    probe_reason = "provider executable not found"
    if executable_path and platform_compatible:
        if spec.probe_args:
            completed = runner.run(
                [executable_name, *spec.probe_args],
                cwd=workspace,
                check=False,
                text=True,
                capture_output=True,
            )
            output = f"{completed.stdout}\n{completed.stderr}".lower()
            failure_marker = next((marker for marker in spec.failure_markers if marker in output), None)
            probe_ok = completed.returncode == 0 and failure_marker is None
            probe_reason = (
                "provider capability probe passed"
                if probe_ok
                else (
                    f"provider capability probe reported: {failure_marker}"
                    if failure_marker
                    else "provider capability probe failed"
                )
            )
        else:
            probe_ok = True
            probe_reason = "provider executable found"

    plugin_present = spec.plugin is None
    plugin_reason = "built-in Vagrant provider"
    if spec.plugin:
        if vagrant_path:
            completed = runner.run(
                ["vagrant", "plugin", "list"],
                cwd=workspace,
                check=False,
                text=True,
                capture_output=True,
            )
            plugin_present = completed.returncode == 0 and any(
                line.split()[0] == spec.plugin for line in completed.stdout.splitlines() if line.split()
            )
            plugin_reason = "provider plugin installed" if plugin_present else f"missing Vagrant plugin {spec.plugin}"
        else:
            plugin_reason = "Vagrant command not found"

    usable = bool(vagrant_path and platform_compatible and probe_ok and plugin_present)
    reasons = []
    if not vagrant_path:
        reasons.append("Vagrant command not found")
    if not platform_compatible:
        reasons.append(f"provider {provider} is not supported on {host_system}")
    if platform_compatible and not probe_ok:
        reasons.append(probe_reason)
    if not plugin_present:
        reasons.append(plugin_reason)
    return {
        "name": provider,
        "vagrant_name": spec.vagrant_name,
        "usable": usable,
        "platform_compatible": platform_compatible,
        "system": host_system,
        "vagrant_path": vagrant_path,
        "provider_command": executable_name,
        "provider_path": executable_path,
        "capability_probe_ok": probe_ok,
        "plugin": spec.plugin,
        "plugin_present": plugin_present,
        "reason": "; ".join(reasons) if reasons else "Vagrant and selected provider are usable",
        "remediation": _provider_remediation(spec, host_system, vagrant_path is not None),
    }


def configured_local_vm_target(profile_targets: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    targets = profile_targets.get("targets") if isinstance(profile_targets, dict) else None
    if not isinstance(targets, dict):
        return None, None
    candidates = {
        str(name): target
        for name, target in targets.items()
        if isinstance(target, dict) and str(target.get("type") or "") in {"local_vm", "vagrant"}
    }
    preferred = str(profile_targets.get("local_vm_default") or "").strip()
    if preferred:
        target = candidates.get(preferred)
        if target is None:
            raise ValueError(f"local_vm_default names an unknown local VM target: {preferred}")
        return preferred, target
    if len(candidates) > 1:
        choices = ", ".join(sorted(candidates))
        raise ValueError(f"multiple local VM targets are configured; set local_vm_default to one of: {choices}")
    if candidates:
        return next(iter(candidates.items()))
    return None, None


def _first_executable(names: tuple[str, ...], command_locator: Callable[[str], str | None]) -> tuple[str, str | None]:
    for name in names:
        path = command_locator(name)
        if path:
            return name, path
    return names[0], None


def _provider_remediation(spec: VagrantProviderSpec, system: str, vagrant_installed: bool) -> list[str]:
    actions = []
    if not vagrant_installed:
        actions.append("aiplane tools install vagrant --dry-run")
    if system not in spec.systems:
        actions.append(f"select a Vagrant provider supported on {system}")
    else:
        actions.append(f"install and enable the {spec.name} provider executable")
    if spec.plugin:
        actions.append(f"vagrant plugin install {spec.plugin}")
    actions.append("aiplane environment doctor --workflow local_vm")
    return actions
