from __future__ import annotations

import json
from pathlib import Path

from aiplane.config import load_profile
from aiplane.deploy import DeployManager

from .cli_fixtures import run_cli


def test_profile_loads_from_synthetic_profile_root() -> None:
    profile = load_profile("local-dev", Path.cwd())
    assert profile.name == "local-dev"
    assert "fixture-analysis-small" in profile.models["models"]


def test_cli_dispatches_config_templates() -> None:
    result = run_cli(["config", "templates"])
    assert result.code == 0
    assert "local" in result.stdout.splitlines()


def test_deployment_plan_is_non_mutating() -> None:
    profile = load_profile("local-dev", Path.cwd())
    plan = DeployManager(profile).workflow_plan("azure_gpu_vm")
    assert plan["workflow"] == "cloud_vm"
    assert plan["mutation_policy"]["default"] == "plan_and_doctor_first"


def test_cli_json_output_serializes() -> None:
    result = run_cli(["profiles", "show", "local-dev", "--selected"])
    assert result.code == 0
    assert json.loads(result.stdout)["name"] == "local-dev"
