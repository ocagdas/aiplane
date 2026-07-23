from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def render_deployment_artifacts(
    target_name: str,
    target: dict[str, Any],
    workflow: str,
    tool_owners: list[str],
) -> dict[str, Any]:
    files = _files(target_name, target, workflow)
    return {
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
        "files": files,
        "checksums": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in files.items()},
        "next_commands": _commands(workflow),
        "notes": [
            "These files are deterministic render-only starters; aiplane does not apply them.",
            "Review provider settings, images, networking, identity, quota, and cost before using an external tool.",
            "Credential values are not embedded. External tools retain authentication and mutation ownership.",
        ],
    }


def _files(target_name: str, target: dict[str, Any], workflow: str) -> dict[str, str]:
    if workflow == "cloud_vm" and target.get("type") == "azure_vm":
        return _azure_vm(target_name, target)
    if workflow == "cloud_kubernetes" and target.get("type") == "azure_aks":
        return _azure_aks(target_name, target)
    if workflow in {"remote_workstation", "remote_vm"}:
        return _remote(target, workflow)
    if workflow == "local_vm":
        return _local_vm(target_name, target)
    if workflow == "local_install":
        return _local_install(target_name)
    raise ValueError(f"deployment artifact rendering is not supported for workflow: {workflow}")


def _commands(workflow: str) -> list[str]:
    if workflow in {"cloud_vm", "cloud_kubernetes"}:
        return [
            "tofu init",
            "tofu validate",
            "tofu plan",
            "terraform init",
            "terraform validate",
            "terraform plan",
        ]
    if workflow in {"remote_workstation", "remote_vm"}:
        return [
            "ansible-inventory -i inventory.ini --list",
            "ansible-playbook -i inventory.ini playbook.yml --check",
        ]
    if workflow == "local_vm":
        return ["vagrant validate", "vagrant up --provision-with ansible"]
    return ["devcontainer up --workspace-folder ."]


def _hcl(value: Any) -> str:
    return json.dumps(str(value or ""))


def _azure_vm(target_name: str, target: dict[str, Any]) -> dict[str, str]:
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
        "main.tf": main_tf,
        "aiplane.pkr.hcl": packer,
        "inventory.ini": f"[aiplane_hosts]\n# replace-with-private-host ansible_user={user_value}\n",
        "playbook.yml": _playbook("cloud_vm"),
    }


def _azure_aks(target_name: str, target: dict[str, Any]) -> dict[str, str]:
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
        "README.md": "# AKS infrastructure starter\n\nRun `tofu validate` and `tofu plan` after adding reviewed resources. This render does not apply infrastructure.\n",
    }


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
    vagrantfile = f"""Vagrant.configure("2") do |config|
  config.vm.box = ENV.fetch("AIPLANE_VAGRANT_BOX", "ubuntu/jammy64")
  config.vm.hostname = {json.dumps(target_name)}
  config.vm.provider "virtualbox" do |provider|
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
