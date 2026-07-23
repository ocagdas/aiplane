from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aiplane.deploy import DeployManager

from .artifact_fixtures import profile_with_local_vm_target, profile_with_target_iac
from .profile_fixtures import load_profile
from .runtime_fixtures import PRIMARY_RUNTIME_FIXTURES, catalog_for_runtime_fixture

SCHEMA_ROOT = Path(__file__).parents[1] / "schemas"


def _schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def test_every_packaged_schema_is_valid_draft_2020_12() -> None:
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("target_name", ["azure_gpu_vm", "aks_gpu_pool"])
@pytest.mark.parametrize("iac", ["opentofu", "terraform", "pulumi"])
def test_selected_iac_deployment_artifacts_validate_against_public_schema(target_name: str, iac: str) -> None:
    source = load_profile("local-dev", Path.cwd())
    payload = DeployManager(profile_with_target_iac(source, target_name, iac)).render(target_name)
    Draft202012Validator(_schema("aiplane-deployment-artifacts-v1.schema.json")).validate(payload)


@pytest.mark.parametrize("provider", ["virtualbox", "libvirt", "hyperv", "vmware_desktop"])
def test_local_vm_provider_artifacts_validate_against_public_schema(provider: str) -> None:
    source = load_profile("local-dev", Path.cwd())
    payload = DeployManager(profile_with_local_vm_target(source, provider)).render("local_dev_vm")
    Draft202012Validator(_schema("aiplane-deployment-artifacts-v1.schema.json")).validate(payload)


def test_non_cloud_deployment_artifacts_validate_against_public_schema() -> None:
    payload = DeployManager(load_profile("local-dev", Path.cwd())).render("gpu_workstation_ssh")
    Draft202012Validator(_schema("aiplane-deployment-artifacts-v1.schema.json")).validate(payload)


@pytest.mark.parametrize("runtime", sorted(PRIMARY_RUNTIME_FIXTURES))
def test_primary_runner_bundles_validate_against_public_schema(runtime: str) -> None:
    catalog, alias, fixture = catalog_for_runtime_fixture(runtime)
    payload = catalog.bundle_plan(runtime, alias, **fixture["bundle_options"])
    Draft202012Validator(_schema("aiplane-runtime-bundle-v1.schema.json")).validate(payload)
