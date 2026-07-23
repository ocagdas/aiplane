from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from aiplane.deploy import DeployManager

from .artifact_fixtures import (
    materialize_artifact_files,
    profile_with_local_vm_target,
    profile_with_target_iac,
)
from .profile_fixtures import load_profile
from aiplane.vagrant_providers import inspect_vagrant_provider

pytestmark = [
    pytest.mark.external_validation,
    pytest.mark.skipif(
        os.environ.get("AIPLANE_RUN_EXTERNAL_VALIDATORS") != "1",
        reason="set AIPLANE_RUN_EXTERNAL_VALIDATORS=1 to run installed external artifact validators",
    ),
]


def _require_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        pytest.skip(f"{name} is not installed")
    return command


def _run(command: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=60, check=False)
    assert completed.returncode == 0, (
        f"external validator failed: {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


@pytest.mark.parametrize(("iac", "command"), [("opentofu", "tofu"), ("terraform", "terraform")])
def test_hcl_scaffold_passes_selected_formatter(tmp_path: Path, iac: str, command: str) -> None:
    executable = _require_command(command)
    profile = profile_with_target_iac(load_profile("local-dev", Path.cwd()), "azure_gpu_vm", iac)
    materialize_artifact_files(DeployManager(profile).render("azure_gpu_vm"), tmp_path)
    _run([executable, "fmt", "-check", "main.tf"], tmp_path)


def test_packer_scaffold_passes_formatter(tmp_path: Path) -> None:
    executable = _require_command("packer")
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("azure_gpu_vm")
    materialize_artifact_files(payload, tmp_path)
    _run([executable, "fmt", "-check", "aiplane.pkr.hcl"], tmp_path)


def test_ansible_scaffold_passes_inventory_and_syntax_validation(tmp_path: Path) -> None:
    inventory = _require_command("ansible-inventory")
    playbook = _require_command("ansible-playbook")
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("gpu_workstation_ssh")
    materialize_artifact_files(payload, tmp_path)
    _run([inventory, "-i", "inventory.ini", "--list"], tmp_path)
    _run([playbook, "-i", "inventory.ini", "playbook.yml", "--syntax-check"], tmp_path)


def test_vagrant_scaffold_passes_validation_with_selected_provider(tmp_path: Path) -> None:
    executable = _require_command("vagrant")
    source = load_profile("local-dev", Path.cwd())
    profile = profile_with_local_vm_target(source, "virtualbox")
    status = inspect_vagrant_provider("virtualbox", workspace=tmp_path)
    if not status["usable"]:
        pytest.skip(str(status["reason"]))
    materialize_artifact_files(DeployManager(profile).render("local_dev_vm"), tmp_path)
    env = {**os.environ, "VAGRANT_DEFAULT_PROVIDER": "virtualbox"}
    _run([executable, "validate"], tmp_path, env=env)


def test_pulumi_scaffold_passes_local_backend_preview(tmp_path: Path) -> None:
    executable = _require_command("pulumi")
    if importlib.util.find_spec("pulumi") is None:
        pytest.skip("the Pulumi Python package is not installed")
    profile = profile_with_target_iac(load_profile("local-dev", Path.cwd()), "azure_gpu_vm", "pulumi")
    materialize_artifact_files(DeployManager(profile).render("azure_gpu_vm"), tmp_path)
    backend = tmp_path / "pulumi-state"
    env = {
        **os.environ,
        "PULUMI_BACKEND_URL": backend.as_uri(),
        "PULUMI_CONFIG_PASSPHRASE": "",
    }
    _run([executable, "login", backend.as_uri(), "--non-interactive"], tmp_path, env=env)
    _run([executable, "stack", "init", "validation", "--non-interactive"], tmp_path, env=env)
    _run([executable, "preview", "--diff", "--non-interactive", "--stack", "validation"], tmp_path, env=env)
