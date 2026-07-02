from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from .models import Profile


@dataclass(frozen=True)
class CommandStep:
    name: str
    command: list[str]
    mutates: bool = False


class DeployManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.targets or {}

    def list(self) -> list[dict[str, Any]]:
        targets = self._targets()
        rows = []
        for name, target in targets.items():
            if isinstance(target, dict):
                rows.append(
                    {
                        "name": name,
                        "type": target.get("type"),
                        "control_cli": target.get("control_cli"),
                        "resource_group": target.get("resource_group"),
                        "region": target.get("region"),
                        "cluster": target.get("cluster"),
                        "vm": target.get("name"),
                        "size": target.get("size"),
                        "namespace": target.get("namespace"),
                    }
                )
        return rows

    def show(self, name: str | None = None) -> dict[str, Any]:
        target_name, target = self._target(name)
        return {"name": target_name, "target": target}

    def plan(self, name: str | None = None) -> dict[str, Any]:
        target_name, target = self._target(name)
        target_type = target.get("type")
        if target_type == "azure_aks":
            steps = _azure_aks_steps(target)
            return {
                "target": target_name,
                "type": "azure_aks",
                "first_control_tool": "az",
                "required_tools": ["az", "kubectl"],
                "config": {
                    "subscription": target.get("subscription"),
                    "resource_group": target.get("resource_group"),
                    "cluster": target.get("cluster"),
                    "namespace": target.get("namespace"),
                    "runtime": target.get("runtime"),
                    "provider": target.get("provider"),
                    "image": target.get("image"),
                },
                "steps": [step.__dict__ for step in steps],
                "notes": [
                    "plan/apply uses Azure CLI first, then kubectl for cluster-scoped operations",
                    "apply is intentionally narrow in this milestone; model runtime manifests should be rendered in a later step",
                ],
            }
        if target_type == "azure_vm":
            steps = _azure_vm_steps(target)
            return {
                "target": target_name,
                "type": "azure_vm",
                "first_control_tool": "az",
                "required_tools": ["az", "ssh"],
                "config": {
                    "subscription": target.get("subscription"),
                    "resource_group": target.get("resource_group"),
                    "region": target.get("region"),
                    "name": target.get("name"),
                    "image": target.get("image"),
                    "size": target.get("size"),
                    "runtime": target.get("runtime"),
                    "provider": target.get("provider"),
                    "access": target.get("access"),
                    "network": target.get("network"),
                },
                "resource_classes": target.get("resource_classes", {}),
                "steps": [step.__dict__ for step in steps],
                "notes": [
                    "Azure VM apply runs the mutating az commands shown in this plan",
                    "Validate regional SKU availability, quota, and cost before provisioning GPU sizes",
                    "Use SSH tunneling, VPN/private networking, or Azure API Management in front of model endpoints for shared use",
                ],
            }
        raise ValueError(f"unsupported deploy target type: {target_type}")

    def doctor(self, name: str | None = None) -> dict[str, Any]:
        target_name, target = self._target(name)
        plan = self.plan(target_name)
        checks: list[dict[str, Any]] = []
        for tool in plan["required_tools"]:
            path = shutil.which(tool)
            checks.append(
                {
                    "name": f"tool:{tool}",
                    "ok": path is not None,
                    "detail": path or "not found on PATH",
                }
            )

        if shutil.which("az"):
            checks.append(_run_check("az:account", ["az", "account", "show", "--output", "json"]))
            resource_group = str(target.get("resource_group") or "")
            cluster = str(target.get("cluster") or "")
            vm_name = str(target.get("name") or "")
            region = str(target.get("region") or "")
            size = str(target.get("size") or "")
            if resource_group:
                checks.append(
                    _run_check(
                        "az:group-show",
                        [
                            "az",
                            "group",
                            "show",
                            "--name",
                            resource_group,
                            "--output",
                            "json",
                        ],
                    )
                )
            if resource_group and cluster:
                checks.append(
                    _run_check(
                        "az:aks-show",
                        [
                            "az",
                            "aks",
                            "show",
                            "--resource-group",
                            resource_group,
                            "--name",
                            cluster,
                            "--output",
                            "json",
                        ],
                    )
                )
            if region and size:
                checks.append(
                    _run_check(
                        "az:vm-sku",
                        [
                            "az",
                            "vm",
                            "list-skus",
                            "--location",
                            region,
                            "--size",
                            size,
                            "--all",
                            "--output",
                            "json",
                        ],
                    )
                )
            if resource_group and vm_name:
                checks.append(
                    _run_check(
                        "az:vm-show",
                        [
                            "az",
                            "vm",
                            "show",
                            "--resource-group",
                            resource_group,
                            "--name",
                            vm_name,
                            "--output",
                            "json",
                        ],
                    )
                )
        else:
            checks.append(
                {
                    "name": "az:account",
                    "ok": False,
                    "detail": "az CLI is required for the first Azure target",
                }
            )
        return {"target": target_name, "checks": checks}

    def apply(self, name: str | None = None, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("deploy apply is mutating; run deploy plan first")
        target_name, target = self._target(name)
        if target.get("type") == "azure_aks":
            apply_steps = _azure_aks_apply_steps(target)
        elif target.get("type") == "azure_vm":
            apply_steps = _azure_vm_apply_steps(target)
        else:
            raise ValueError(f"deploy apply is not implemented for target type: {target.get('type')}")
        results = []
        for step in apply_steps:
            completed = subprocess.run(step.command, text=True, capture_output=True, check=False)
            results.append(
                {
                    "name": step.name,
                    "command": step.command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }
            )
            if completed.returncode != 0:
                break
        return {"target": target_name, "results": results}

    def _targets(self) -> dict[str, Any]:
        targets = self.config.get("targets", {})
        if not isinstance(targets, dict):
            return {}
        return targets

    def _target(self, name: str | None) -> tuple[str, dict[str, Any]]:
        target_name = name or str(self.config.get("default") or "")
        targets = self._targets()
        target = targets.get(target_name)
        if not target_name or not isinstance(target, dict):
            raise ValueError(f"unknown deploy target: {target_name or '<default>'}")
        return target_name, target


def _azure_vm_steps(target: dict[str, Any]) -> list[CommandStep]:
    resource_group = str(target.get("resource_group") or "")
    region = str(target.get("region") or "")
    name = str(target.get("name") or "")
    image = str(target.get("image") or "Ubuntu2204")
    size = str(target.get("size") or "")
    admin_user = str(target.get("admin_user") or "azureuser")
    ssh_key = str(target.get("ssh_key") or "~/.ssh/id_rsa.pub")
    public_ip = (
        bool((target.get("network") or {}).get("public_ip", False))
        if isinstance(target.get("network"), dict)
        else False
    )
    create = [
        "az",
        "vm",
        "create",
        "--resource-group",
        resource_group,
        "--name",
        name,
        "--image",
        image,
        "--size",
        size,
        "--admin-username",
        admin_user,
        "--ssh-key-values",
        ssh_key,
    ]
    if not public_ip:
        create.extend(["--public-ip-address", ""])
    steps = [
        CommandStep("check Azure login", ["az", "account", "show", "--output", "json"]),
        CommandStep(
            "create or confirm resource group",
            ["az", "group", "create", "--name", resource_group, "--location", region],
            mutates=True,
        ),
        CommandStep(
            "check VM SKU availability",
            [
                "az",
                "vm",
                "list-skus",
                "--location",
                region,
                "--size",
                size,
                "--all",
                "--output",
                "table",
            ],
        ),
        CommandStep("create VM", create, mutates=True),
        CommandStep(
            "show VM addresses",
            [
                "az",
                "vm",
                "list-ip-addresses",
                "--resource-group",
                resource_group,
                "--name",
                name,
                "--output",
                "table",
            ],
        ),
        CommandStep("ssh to VM", ["ssh", f"{admin_user}@<vm-ip>"]),
    ]
    if public_ip:
        steps.insert(
            4,
            CommandStep(
                "open SSH port",
                [
                    "az",
                    "vm",
                    "open-port",
                    "--resource-group",
                    resource_group,
                    "--name",
                    name,
                    "--port",
                    "22",
                ],
                mutates=True,
            ),
        )
    return steps


def _azure_aks_steps(target: dict[str, Any]) -> list[CommandStep]:
    resource_group = str(target.get("resource_group") or "")
    cluster = str(target.get("cluster") or "")
    namespace = str(target.get("namespace") or "default")
    steps = [
        CommandStep("check Azure login", ["az", "account", "show", "--output", "json"]),
        CommandStep(
            "check AKS cluster",
            [
                "az",
                "aks",
                "show",
                "--resource-group",
                resource_group,
                "--name",
                cluster,
                "--output",
                "json",
            ],
        ),
        CommandStep(
            "load AKS credentials",
            [
                "az",
                "aks",
                "get-credentials",
                "--resource-group",
                resource_group,
                "--name",
                cluster,
                "--overwrite-existing",
            ],
            mutates=True,
        ),
        CommandStep("check Kubernetes nodes", ["kubectl", "get", "nodes", "-o", "wide"]),
        CommandStep(
            "create namespace",
            ["kubectl", "create", "namespace", namespace],
            mutates=True,
        ),
    ]
    return steps


def _azure_vm_apply_steps(target: dict[str, Any]) -> list[CommandStep]:
    return [step for step in _azure_vm_steps(target) if step.mutates]


def _azure_aks_apply_steps(target: dict[str, Any]) -> list[CommandStep]:
    return [step for step in _azure_aks_steps(target) if step.mutates]


def _run_check(name: str, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    detail = completed.stdout.strip() or completed.stderr.strip() or f"exit {completed.returncode}"
    return {"name": name, "ok": completed.returncode == 0, "detail": detail[-2000:]}
