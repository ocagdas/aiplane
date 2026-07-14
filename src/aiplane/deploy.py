from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner
from .models import Profile


@dataclass(frozen=True)
class CommandStep:
    name: str
    command: list[str]
    mutates: bool = False


class DeployManager:
    def __init__(self, profile: Profile, command_runner: CommandRunner | None = None):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
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

    def workflow_plan(self, name: str | None = None) -> dict[str, Any]:
        target_name, target = self._target(name)
        target_type = str(target.get("type") or "")
        workflow = _workflow_for_target(target_name, target)
        return {
            "target": target_name,
            "type": target_type,
            "workflow": workflow,
            "phases": _workflow_phases(workflow, target),
            "boundaries": {
                "local_install": workflow == "local_install",
                "local_vm_provisioning": workflow == "local_vm",
                "remote_existing_machine_setup": workflow in {"remote_workstation", "remote_vm"},
                "cloud_resource_provisioning": workflow in {"cloud_vm", "cloud_kubernetes"},
            },
            "mutation_policy": _workflow_mutation_policy(workflow),
            "recommended_tools": _workflow_tools(workflow, target),
            "notes": [
                "This workflow plan is non-mutating and separates host setup, access, endpoint exposure, and cloud provisioning responsibilities.",
                "Use deploy plan/doctor for target-specific commands, remote tunnel plan for SSH access, and stacks endpoint-plan before sharing endpoints.",
            ],
        }

    def plan(self, name: str | None = None) -> dict[str, Any]:
        target_name, target = self._target(name)
        target_type = target.get("type")
        workflow = self.workflow_plan(target_name)
        if target_type == "azure_aks":
            steps = _azure_aks_steps(target)
            return {
                "target": target_name,
                "type": "azure_aks",
                "workflow": workflow["workflow"],
                "workflow_boundaries": workflow["boundaries"],
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
                "workflow": workflow["workflow"],
                "workflow_boundaries": workflow["boundaries"],
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
            checks.append(
                _run_check("az:account", ["az", "account", "show", "--output", "json"], runner=self.command_runner)
            )
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
                        runner=self.command_runner,
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
                        runner=self.command_runner,
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
                        runner=self.command_runner,
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
                        runner=self.command_runner,
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
            completed = self.command_runner.run(step.command, text=True, capture_output=True, check=False)
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


def _workflow_for_target(target_name: str, target: dict[str, Any]) -> str:
    target_type = str(target.get("type") or "")
    if target_type == "azure_aks":
        return "cloud_kubernetes"
    if target_type == "azure_vm":
        return "cloud_vm"
    if target_type == "ssh_tunnel":
        return "remote_workstation"
    if target_type in {"local_vm", "vagrant"}:
        return "local_vm"
    if target_type in {"same_host", "local"}:
        return "local_install"
    if "vm" in target_name and str((target.get("access") or {}).get("mode") or "") == "ssh_tunnel":
        return "remote_vm"
    return "custom_remote"


def _workflow_tools(workflow: str, target: dict[str, Any]) -> list[str]:
    if workflow == "cloud_kubernetes":
        return ["az", "kubectl", "helm", "opentofu", "terraform", "pulumi"]
    if workflow == "cloud_vm":
        return ["az", "ssh", "opentofu", "terraform", "pulumi", "packer", "ansible"]
    if workflow == "remote_workstation":
        return ["ssh", "ansible"]
    if workflow == "remote_vm":
        return ["ssh", "ansible", "packer"]
    if workflow == "local_vm":
        return ["vagrant", "packer", "ansible"]
    if workflow == "local_install":
        return ["docker", "conda", "venv"]
    return [str(target.get("control_cli") or "ssh")]


def _workflow_mutation_policy(workflow: str) -> dict[str, Any]:
    if workflow in {"cloud_vm", "cloud_kubernetes"}:
        return {
            "default": "plan_and_doctor_first",
            "apply": "guarded_cli_only",
            "mcp": "read_plan_only",
            "notes": "cloud provisioning must stay explicit, reviewed, and outside MCP broad write surfaces",
        }
    if workflow in {"remote_workstation", "remote_vm"}:
        return {
            "default": "ssh_plan_first",
            "apply": "manual_or_guarded_remote_tooling",
            "mcp": "read_plan_only",
            "notes": "remote host mutation should go through SSH/Ansible plans with explicit operator review",
        }
    if workflow == "local_vm":
        return {
            "default": "vagrant_packer_plan_first",
            "apply": "external_tool_cli",
            "mcp": "read_plan_only",
            "notes": "local VM lifecycle belongs to Vagrant/Packer, not hidden aiplane mutation",
        }
    return {
        "default": "local_doctor_plan_setup",
        "apply": "same_host_helpers_where_supported",
        "mcp": "narrow_guarded_writes_only",
        "notes": "same-host setup can use existing helper paths when available",
    }


def _workflow_phases(workflow: str, target: dict[str, Any]) -> list[dict[str, Any]]:
    if workflow == "cloud_kubernetes":
        return [
            {"name": "cloud account and quota", "tool_owner": "az", "mutates": False},
            {"name": "cluster access", "tool_owner": "az/kubectl", "mutates": True},
            {
                "name": "runtime manifests",
                "tool_owner": "kubectl/helm",
                "mutates": True,
            },
            {
                "name": "endpoint auth/gateway",
                "tool_owner": "gateway/APIM/Ingress",
                "mutates": True,
            },
        ]
    if workflow == "cloud_vm":
        return [
            {
                "name": "cloud account, region, quota, and SKU",
                "tool_owner": "az",
                "mutates": False,
            },
            {
                "name": "VM/resource group provisioning",
                "tool_owner": "az/OpenTofu/Terraform/Pulumi",
                "mutates": True,
            },
            {
                "name": "host configuration",
                "tool_owner": "SSH/Ansible/cloud-init",
                "mutates": True,
            },
            {
                "name": "runtime stack setup",
                "tool_owner": "aiplane stacks prepare/start or runtime helper",
                "mutates": True,
            },
            {
                "name": "endpoint access",
                "tool_owner": "SSH tunnel/VPN/gateway",
                "mutates": False,
            },
        ]
    if workflow in {"remote_workstation", "remote_vm"}:
        return [
            {
                "name": "remote inventory/profile",
                "tool_owner": "machines profile-remote-plan",
                "mutates": False,
            },
            {
                "name": "SSH access",
                "tool_owner": "remote tunnel plan/start",
                "mutates": True,
            },
            {
                "name": "host configuration",
                "tool_owner": "manual SSH/Ansible",
                "mutates": True,
            },
            {
                "name": "endpoint access",
                "tool_owner": "SSH tunnel/VPN/gateway",
                "mutates": False,
            },
        ]
    if workflow == "local_vm":
        return [
            {
                "name": "image/box selection",
                "tool_owner": "Packer/Vagrant",
                "mutates": False,
            },
            {"name": "local VM lifecycle", "tool_owner": "Vagrant", "mutates": True},
            {
                "name": "inside-VM setup",
                "tool_owner": "setup_env/environment doctor",
                "mutates": True,
            },
        ]
    return [
        {
            "name": "local tool doctor",
            "tool_owner": "environment/tools doctor",
            "mutates": False,
        },
        {"name": "runtime setup", "tool_owner": "runtime helper", "mutates": True},
        {
            "name": "endpoint export",
            "tool_owner": "integrations/stacks export",
            "mutates": False,
        },
    ]


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


def _run_check(name: str, command: list[str], *, runner: CommandRunner) -> dict[str, Any]:
    completed = runner.run(command, text=True, capture_output=True, check=False)
    detail = completed.stdout.strip() or completed.stderr.strip() or f"exit {completed.returncode}"
    return {"name": name, "ok": completed.returncode == 0, "detail": detail[-2000:]}
