from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from aiplane.cli import main
from aiplane.config import load_profile
from aiplane.deploy import DeployManager


def test_profile_loads_from_synthetic_profile_root() -> None:
    profile = load_profile("local-dev", Path.cwd())
    assert profile.name == "local-dev"
    assert "fixture-analysis-small" in profile.models["models"]


def test_cli_dispatches_config_templates() -> None:
    stdout = StringIO()
    with redirect_stdout(stdout):
        result = main(["config", "templates"])
    assert result == 0
    assert "local" in stdout.getvalue().splitlines()


def test_deployment_plan_is_non_mutating() -> None:
    profile = load_profile("local-dev", Path.cwd())
    plan = DeployManager(profile).workflow_plan("azure_gpu_vm")
    assert plan["workflow"] == "cloud_vm"
    assert plan["mutation_policy"]["default"] == "plan_and_doctor_first"


def test_cli_json_output_serializes() -> None:
    stdout = StringIO()
    with redirect_stdout(stdout):
        result = main(["profiles", "show", "local-dev", "--selected"])
    assert result == 0
    assert json.loads(stdout.getvalue())["name"] == "local-dev"
