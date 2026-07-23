"""Application-level invariants for generated artifact contracts."""

from __future__ import annotations

import hashlib
from typing import Any


def validate_runtime_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_file_checksums(payload, "runtime bundle")
    files = payload["files"]
    selected_file = payload.get("selected_file")
    if selected_file not in files:
        raise ValueError("runtime bundle selected_file must name an emitted file")
    if set(files) != {selected_file}:
        raise ValueError("runtime bundle must emit only the selected_file")
    expected_file = {
        "docker": "Dockerfile",
        "conda": "environment.yaml",
        "native": "runtime-launch.json",
    }.get(payload.get("mode"))
    if expected_file is None:
        raise ValueError("runtime bundle mode must be docker, conda, or native")
    if selected_file != expected_file:
        raise ValueError(f"runtime bundle mode requires selected_file {expected_file!r}")
    supported_modes = payload.get("supported_modes")
    if not isinstance(supported_modes, list) or payload.get("mode") not in supported_modes:
        raise ValueError("runtime bundle mode must be present in supported_modes")
    return payload


def validate_deployment_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    _validate_file_checksums(payload, "deployment artifacts")
    if payload.get("render_only") is not True or payload.get("apply_supported") is not False:
        raise ValueError("deployment artifacts must remain render-only with apply unsupported")
    _validate_iac_artifacts(payload)
    return payload


def _validate_iac_artifacts(payload: dict[str, Any]) -> None:
    workflow = payload.get("workflow")
    iac = payload.get("iac")
    if workflow not in {"cloud_vm", "cloud_kubernetes"}:
        if iac is not None:
            raise ValueError("non-cloud deployment artifacts must not declare an IaC implementation")
        _validate_vm_provider_artifacts(payload)
        return
    if iac not in {"opentofu", "terraform", "pulumi"}:
        raise ValueError("cloud deployment artifacts must declare a supported IaC implementation")
    files = set(payload["files"])
    validation_commands = payload.get("validation_commands")
    if not isinstance(validation_commands, list) or not validation_commands:
        raise ValueError("cloud deployment artifacts must provide validation commands")
    if iac == "pulumi":
        required = {"Pulumi.yaml", "requirements.txt", "__main__.py"}
        if not required <= files or "main.tf" in files:
            raise ValueError("Pulumi deployment artifacts must emit a Pulumi project and no HCL module")
        if validation_commands != ["pulumi preview --diff"]:
            raise ValueError("Pulumi deployment artifacts must use pulumi preview validation")
        return
    if "main.tf" not in files or "Pulumi.yaml" in files or "__main__.py" in files:
        raise ValueError("HCL deployment artifacts must emit main.tf and no Pulumi project")
    command = "tofu" if iac == "opentofu" else "terraform"
    if validation_commands != [f"{command} fmt -check"]:
        raise ValueError(f"{iac} deployment artifacts must use {command} validation")


def _validate_vm_provider_artifacts(payload: dict[str, Any]) -> None:
    workflow = payload.get("workflow")
    provider = payload.get("vm_provider")
    if workflow != "local_vm":
        if provider is not None:
            raise ValueError("non-local-VM deployment artifacts must not declare a Vagrant provider")
        return
    supported = {"virtualbox", "libvirt", "hyperv", "vmware_desktop"}
    if provider not in supported:
        raise ValueError("local VM deployment artifacts must declare a supported Vagrant provider")
    files = payload["files"]
    if not {"Vagrantfile", "playbook.yml"} <= set(files):
        raise ValueError("local VM deployment artifacts must emit Vagrantfile and playbook.yml")
    expected = f'config.vm.provider "{provider}"'
    if expected not in files["Vagrantfile"]:
        raise ValueError("local VM Vagrantfile must match the declared Vagrant provider")
    if payload.get("validation_commands") != ["vagrant validate"]:
        raise ValueError("local VM deployment artifacts must use vagrant validate")


def _validate_file_checksums(payload: dict[str, Any], label: str) -> None:
    files = payload.get("files")
    checksums = payload.get("checksums")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"{label} files must be a non-empty object")
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError(f"{label} checksums must be a non-empty object")
    if set(files) != set(checksums):
        raise ValueError(f"{label} file and checksum keys must match")
    for name, content in files.items():
        if not isinstance(content, str):
            raise ValueError(f"{label} file {name!r} must contain text")
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if checksums[name] != expected:
            raise ValueError(f"{label} checksum mismatch for {name!r}")
