from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .artifact_validation import validate_deployment_artifacts
from .vagrant_providers import VAGRANT_PROVIDERS, selected_vagrant_provider


def render_deployment_artifacts(
    target_name: str,
    target: dict[str, Any],
    workflow: str,
    tool_owners: list[str],
) -> dict[str, Any]:
    iac = iac_implementation(target) if workflow in {"cloud_vm", "cloud_kubernetes"} else None
    files = _files(target_name, target, workflow, iac)
    readiness, unresolved_inputs = _artifact_readiness(workflow, target)
    validation_commands = _validation_commands(workflow, iac)
    payload = {
        "$schema": "schemas/aiplane-deployment-artifacts-v1.schema.json",
        "schema_version": "1.0",
        "record_type": "deployment_artifacts",
        "render_only": True,
        "apply_supported": False,
        "review_required": True,
        "target": target_name,
        "target_type": str(target.get("type") or ""),
        "workflow": workflow,
        "tool_owners": tool_owners,
        "iac": iac,
        "vm_provider": selected_vagrant_provider(target) if workflow == "local_vm" else None,
        "artifact_readiness": readiness,
        "unresolved_inputs": unresolved_inputs,
        "files": files,
        "checksums": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()},
        "validation_commands": validation_commands,
        "next_commands": validation_commands if readiness == "validate_ready" else [],
        "notes": [
            "These files are deterministic render-only starters; aiplane does not apply them.",
            "Review provider settings, images, networking, identity, quota, and cost before using an external tool.",
            "Credential values are not embedded. External tools retain authentication and mutation ownership.",
        ],
    }
    return validate_deployment_artifacts(payload)


def _files(
    target_name: str,
    target: dict[str, Any],
    workflow: str,
    iac: str | None,
) -> dict[str, str]:
    if workflow in {"cloud_vm", "cloud_kubernetes"} and iac is None:
        raise ValueError("cloud deployment artifact rendering requires an IaC implementation")
    if workflow == "cloud_vm" and target.get("type") == "azure_vm":
        return _azure_vm(target_name, target, iac)
    if workflow == "cloud_kubernetes" and target.get("type") == "azure_aks":
        return _azure_aks(target_name, target, iac)
    if workflow in {"remote_workstation", "remote_vm"}:
        return _remote(target, workflow)
    if workflow == "local_vm":
        return _local_vm(target_name, target)
    if workflow == "local_install":
        return _local_install(target_name)
    raise ValueError(f"deployment artifact rendering is not supported for workflow: {workflow}")


def iac_implementation(target: dict[str, Any]) -> str:
    selected = str(target.get("iac") or "opentofu").strip().lower()
    if selected not in {"opentofu", "terraform", "pulumi"}:
        raise ValueError("target iac must be opentofu, terraform, or pulumi")
    return selected


def _validation_commands(workflow: str, iac: str | None) -> list[str]:
    if workflow in {"cloud_vm", "cloud_kubernetes"}:
        if iac == "pulumi":
            return ["pulumi preview --diff"]
        command = "tofu" if iac == "opentofu" else "terraform"
        return [f"{command} fmt -check"]
    if workflow in {"remote_workstation", "remote_vm"}:
        return [
            "ansible-inventory -i inventory.ini --list",
            "ansible-playbook -i inventory.ini playbook.yml --syntax-check",
        ]
    if workflow == "local_vm":
        return ["vagrant validate"]
    return ["devcontainer read-configuration --workspace-folder ."]


def _artifact_readiness(workflow: str, target: dict[str, Any]) -> tuple[str, list[str]]:
    if workflow == "cloud_vm":
        return "scaffold", [
            "reviewed infrastructure resource blocks",
            "network and identity design",
            "immutable VM image reference",
            "active Ansible inventory host",
            "Packer source and build blocks",
        ]
    if workflow == "cloud_kubernetes":
        return "scaffold", [
            "reviewed resource group, cluster, identity, network, and node-pool resources",
            "immutable workload image references",
        ]
    if workflow in {"remote_workstation", "remote_vm"}:
        ssh = target.get("ssh") if isinstance(target.get("ssh"), dict) else {}
        unresolved = []
        if not ssh.get("host"):
            unresolved.append("ssh.host")
        if not ssh.get("user"):
            unresolved.append("ssh.user")
        return ("scaffold", unresolved) if unresolved else ("validate_ready", [])
    if workflow == "local_vm":
        return "validate_ready", []
    return "validate_ready", []


def _hcl(value: Any) -> str:
    return json.dumps(str(value or ""))


def _azure_vm(target_name: str, target: dict[str, Any], iac: str) -> dict[str, str]:
    if iac == "pulumi":
        return _azure_vm_pulumi(target_name, target)
    name = _hcl(target.get("name") or target_name)
    group = _hcl(target.get("resource_group") or "rg-aiplane")
    region = _hcl(target.get("region") or "uksouth")
    size = _hcl(target.get("size") or "Standard_NC4as_T4_v3")
    image = _hcl(target.get("image") or "Ubuntu2204")
    user_value = _safe_inventory_value(
        "admin_user", target.get("admin_user") or "azureuser", r"[A-Za-z_][A-Za-z0-9_.-]*"
    )
    user = _hcl(user_value)
    main_tf = f"""terraform {{
  required_version = ">= 1.6.0"
  required_providers {{
    azurerm = {{ source = "hashicorp/azurerm", version = "~> 4.0" }}
  }}
}}

provider "azurerm" {{ features {{}} }}

variable "ssh_public_key_path" {{ type = string }}
variable "create_resources" {{ type = bool, default = false }}

locals {{
  target_name    = {name}
  resource_group = {group}
  region         = {region}
  vm_size        = {size}
  image_alias    = {image}
  admin_user     = {user}
}}

# This starter intentionally stops before declaring resources. Confirm networking,
# image URNs, identity, storage, quota, and cost, then add reviewed azurerm resources.
# `create_resources` remains false so an unreviewed plan cannot imply approval.
"""
    return {"main.tf": main_tf, **_azure_vm_support_files(group, region, user_value)}


def _azure_aks(target_name: str, target: dict[str, Any], iac: str) -> dict[str, str]:
    if iac == "pulumi":
        return _azure_aks_pulumi(target_name, target)
    group = _hcl(target.get("resource_group") or "rg-aiplane")
    region = _hcl(target.get("region") or "uksouth")
    cluster = _hcl(target.get("cluster") or target_name)
    main_tf = f"""terraform {{
  required_version = ">= 1.6.0"
  required_providers {{
    azurerm = {{ source = "hashicorp/azurerm", version = "~> 4.0" }}
  }}
}}

provider "azurerm" {{ features {{}} }}

locals {{
  resource_group = {group}
  region         = {region}
  cluster_name   = {cluster}
}}

# Add reviewed resource-group, AKS, identity, network, and node-pool resources here.
# Render runtime workload files separately with `aiplane stacks render-kubernetes`.
"""
    return {
        "main.tf": main_tf,
        "README.md": (
            "# AKS infrastructure starter\n\n"
            f"Run `{'tofu' if iac == 'opentofu' else 'terraform'} validate` after adding reviewed resources. "
            "This render does not apply infrastructure.\n"
        ),
    }


def _azure_vm_support_files(group: str, region: str, user_value: str) -> dict[str, str]:
    packer = f"""packer {{
  required_plugins {{
    azure = {{ source = "github.com/hashicorp/azure", version = ">= 2.0.0" }}
  }}
}}

variable "subscription_id" {{ type = string, sensitive = true }}
variable "resource_group" {{ type = string, default = {group} }}
variable "region" {{ type = string, default = {region} }}

# Add a reviewed azure-arm source only after selecting an image publisher/offer/SKU.
# Supply credentials through the Azure CLI or environment; never store them here.
"""
    return {
        "aiplane.pkr.hcl": packer,
        "inventory.ini": f"[aiplane_hosts]\n# replace-with-private-host ansible_user={user_value}\n",
        "playbook.yml": _playbook("cloud_vm"),
    }


def _pulumi_project(target_name: str, description: str, program: str) -> dict[str, str]:
    project_name = re.sub(r"[^a-z0-9-]+", "-", target_name.lower()).strip("-") or "aiplane-target"
    project = f"name: {project_name}\nruntime:\n  name: python\ndescription: {description}\n"
    requirements = "pulumi>=3.0,<4.0\npulumi-azure-native>=3.0,<4.0\n"
    return {
        "Pulumi.yaml": project,
        "requirements.txt": requirements,
        "__main__.py": program,
    }


def _azure_vm_pulumi(target_name: str, target: dict[str, Any]) -> dict[str, str]:
    values = {
        "target_name": str(target.get("name") or target_name),
        "resource_group": str(target.get("resource_group") or "rg-aiplane"),
        "region": str(target.get("region") or "uksouth"),
        "vm_size": str(target.get("size") or "Standard_NC4as_T4_v3"),
        "image_alias": str(target.get("image") or "Ubuntu2204"),
        "admin_user": _safe_inventory_value(
            "admin_user", target.get("admin_user") or "azureuser", r"[A-Za-z_][A-Za-z0-9_.-]*"
        ),
    }
    rendered = json.dumps(values, indent=2, sort_keys=True)
    program = f'''"""Render-only Azure VM Pulumi scaffold generated by aiplane."""

import pulumi

config = pulumi.Config()
defaults = {rendered}

settings = {{key: config.get(key) or value for key, value in defaults.items()}}
for key, value in settings.items():
    pulumi.export(key, value)

# Add reviewed azure-native network, identity, storage, and VM resources here.
# Keep credentials in the Azure CLI or environment; never embed them in this project.
'''
    project = _pulumi_project(target_name, "Render-only Azure VM infrastructure scaffold", program)
    return {
        **project,
        **_azure_vm_support_files(
            _hcl(values["resource_group"]),
            _hcl(values["region"]),
            values["admin_user"],
        ),
    }


def _azure_aks_pulumi(target_name: str, target: dict[str, Any]) -> dict[str, str]:
    values = {
        "resource_group": str(target.get("resource_group") or "rg-aiplane"),
        "region": str(target.get("region") or "uksouth"),
        "cluster_name": str(target.get("cluster") or target_name),
        "node_pool": str(target.get("node_pool") or "gpu"),
    }
    rendered = json.dumps(values, indent=2, sort_keys=True)
    program = f'''"""Render-only Azure AKS Pulumi scaffold generated by aiplane."""

import pulumi

config = pulumi.Config()
defaults = {rendered}

settings = {{key: config.get(key) or value for key, value in defaults.items()}}
for key, value in settings.items():
    pulumi.export(key, value)

# Add reviewed azure-native resource-group, AKS, identity, network, and node-pool resources here.
# Render runtime workload files separately with `aiplane stacks render-kubernetes`.
'''
    return _pulumi_project(target_name, "Render-only Azure AKS infrastructure scaffold", program)


def _remote(target: dict[str, Any], workflow: str) -> dict[str, str]:
    ssh = target.get("ssh") if isinstance(target.get("ssh"), dict) else {}
    host = _safe_inventory_value("ssh.host", ssh.get("host") or "replace-with-host", r"[A-Za-z0-9][A-Za-z0-9._:-]*")
    user = _safe_inventory_value("ssh.user", ssh.get("user") or "replace-with-user", r"[A-Za-z_][A-Za-z0-9_.-]*")
    port = int(ssh.get("port") or 22)
    if not 1 <= port <= 65535:
        raise ValueError("ssh.port must be in the range 1-65535")
    return {
        "inventory.ini": f"[aiplane_hosts]\n{host} ansible_user={user} ansible_port={port}\n",
        "playbook.yml": _playbook(workflow),
    }


def _local_vm(target_name: str, target: dict[str, Any]) -> dict[str, str]:
    cpus = int(target.get("cpus") or 4)
    memory = int(target.get("memory_mb") or 8192)
    if cpus < 1:
        raise ValueError("local VM cpus must be positive")
    if memory < 512:
        raise ValueError("local VM memory_mb must be at least 512")
    provider = selected_vagrant_provider(target)
    vagrant_name = VAGRANT_PROVIDERS[provider].vagrant_name
    box = str(target.get("box") or "bento/ubuntu-24.04")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", box):
        raise ValueError("local VM box contains unsupported characters")
    vagrantfile = f"""Vagrant.configure("2") do |config|
  config.vm.box = ENV.fetch("AIPLANE_VAGRANT_BOX", {json.dumps(box)})
  config.vm.hostname = {json.dumps(target_name)}
  config.vm.provider {json.dumps(vagrant_name)} do |provider|
    provider.cpus = {cpus}
    provider.memory = {memory}
  end
  config.vm.provision "ansible" do |ansible|
    ansible.playbook = "playbook.yml"
  end
end
"""
    return {"Vagrantfile": vagrantfile, "playbook.yml": _playbook("local_vm")}


def _local_install(target_name: str) -> dict[str, str]:
    content = (
        json.dumps(
            {
                "name": target_name,
                "image": "python:3.13-slim",
                "workspaceFolder": "/workspaces/${localWorkspaceFolderBasename}",
                "postCreateCommand": "python -m pip install -e .",
            },
            indent=2,
        )
        + "\n"
    )
    return {".devcontainer/devcontainer.json": content}


def _safe_inventory_value(field: str, value: Any, pattern: str) -> str:
    rendered = str(value)
    if not re.fullmatch(pattern, rendered):
        raise ValueError(f"{field} contains unsupported inventory characters")
    return rendered


def _playbook(workflow: str) -> str:
    return f"""---
- name: Inspect an aiplane host baseline
  hosts: aiplane_hosts
  become: true
  vars:
    aiplane_workflow: {workflow}
  tasks:
    - name: Install baseline packages on Debian-family hosts
      ansible.builtin.apt:
        name: [curl, git, python3, python3-venv, openssh-client]
        update_cache: true
      when: ansible_os_family == "Debian"
    - name: Explain the reviewed next step
      ansible.builtin.debug:
        msg: "Run aiplane environment doctor and runtime prerequisites before runtime setup."
"""
