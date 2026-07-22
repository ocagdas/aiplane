from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from aiplane.adapter_protocol import (
    AdapterModel,
    AdapterRequest,
    AdapterResult,
    run_adapter,
    validate_result,
    validate_result_file,
)
from aiplane.cli import main
from aiplane.config import load_profile, parse_yaml
from aiplane.docker_model_runner import DockerModelRunner
from aiplane.integration_contracts import ALL_INTEGRATION_TOOLS
from aiplane.integration_imports import import_client_config
from aiplane.kubernetes_artifacts import render_kubernetes
from aiplane.profile_schema import canonical_profile, structural_profile_findings
from aiplane.runtime_definitions import RUNTIME_DEFINITIONS, SOURCE_DEFINITIONS
from aiplane.support_catalog import support_catalog, support_record, support_records


class RecordingRunner:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **kwargs):
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def test_support_catalog_covers_public_surfaces() -> None:
    catalog = support_catalog()
    assert set(catalog["runtimes"]) == set(RUNTIME_DEFINITIONS)
    assert set(catalog["providers"]) == set(SOURCE_DEFINITIONS)
    assert set(catalog["clients"]) == set(ALL_INTEGRATION_TOOLS)
    assert support_record("runtime", "docker_model_runner")["support_tier"] == "tier_1"
    assert all(row["upstream_versions"] == [] for row in support_records())


def test_support_cli_is_profile_independent(capsys) -> None:
    assert main(["support", "show", "client", "continue"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "continue"


def test_continue_import_is_preview_first_and_secret_free(tmp_path: Path) -> None:
    config = tmp_path / "continue.json"
    env_reference = "$" + "{OPENAI_API_KEY}"
    config.write_text(
        json.dumps(
            {
                "models": [
                    {"title": "Local Chat", "provider": "ollama", "model": "qwen3:8b", "apiKey": "literal-secret"},
                    {"title": "Cloud Chat", "provider": "openai", "model": "gpt-example", "apiKey": env_reference},
                ]
            }
        )
    )
    profiles = tmp_path / "profiles"
    preview = import_client_config("continue", config, profile_name="imported", profiles_dir=profiles)
    assert preview["preview"] and not (profiles / "imported").exists()
    written = import_client_config("continue", config, profile_name="imported", profiles_dir=profiles, yes=True)
    assert written["written"]
    serialized = (profiles / "imported" / "models.yaml").read_text()
    assert "literal-secret" not in serialized and "OPENAI_API_KEY" in serialized
    repository = parse_yaml((profiles / "imported" / "repository.yaml").read_text())
    findings = structural_profile_findings(canonical_profile(load_profile("imported", tmp_path, profiles_dir=profiles)))
    assert all(finding["ok"] for finding in findings), findings
    assert repository["import_review"] == {
        "status": "unapproved",
        "source_tool": "continue",
        "secrets_copied": False,
        "review_required": True,
    }


def test_aider_yaml_import(tmp_path: Path) -> None:
    config = tmp_path / "aider.yml"
    config.write_text("model: ollama_chat/qwen3:8b\nweak-model: openai/gpt-small\nopenai-api-key: $OPENAI_API_KEY\n")
    payload = import_client_config("aider", config, profile_name="draft", profiles_dir=tmp_path / "profiles")
    assert {row["model"] for row in payload["models"].values()} == {"qwen3:8b", "gpt-small"}
    assert all(row.get("api_key_env") == "OPENAI_API_KEY" for row in payload["models"].values())


def test_adapter_fixture_protocol_and_secret_rejection() -> None:
    fixture_path = Path("tests/fixtures/adapter-v1.json")
    result = validate_result_file(fixture_path)
    assert result.models[0].id == "example/model-7b"

    class Adapter:
        name = "example_adapter"

        def discover(self, request: AdapterRequest) -> AdapterResult:
            return AdapterResult(
                "1.0", self.name, True, (AdapterModel("model-a", request.provider),), {"source": "test"}
            )

    assert run_adapter(Adapter(), AdapterRequest("example")).models[0].provider == "example"
    fixture = json.loads(fixture_path.read_text())
    fixture["api_key"] = "forbidden"
    with pytest.raises(ValueError, match="secret-bearing"):
        validate_result(fixture)


@pytest.mark.parametrize(
    ("action", "model", "command"),
    [
        ("status", "all", ["docker", "model", "status", "--json"]),
        ("list-runtime-models", "all", ["docker", "model", "list", "--format", "json"]),
        ("inspect", "ai/model", ["docker", "model", "inspect", "ai/model"]),
        ("benchmark", "ai/model", ["docker", "model", "bench", "ai/model"]),
        ("install", "all", ["docker", "model", "install-runner"]),
        ("update", "all", ["docker", "model", "reinstall-runner"]),
        ("start", "all", ["docker", "model", "start-runner"]),
        ("stop", "all", ["docker", "model", "stop-runner"]),
        ("restart", "all", ["docker", "model", "restart-runner"]),
        ("pull", "ai/model", ["docker", "model", "pull", "ai/model"]),
        ("remove", "ai/model", ["docker", "model", "rm", "ai/model"]),
        ("clear", "all", ["docker", "model", "purge"]),
    ],
)
def test_docker_model_runner_commands(action, model, command) -> None:
    assert DockerModelRunner.command(action, model=model) == command


def test_docker_model_runner_is_guarded_and_decodes_inventory() -> None:
    runner = RecordingRunner()
    payload, code = DockerModelRunner(runner).run("pull", model="ai/model")
    assert code == 2 and payload["requires_yes"] and not runner.commands
    payload, code = DockerModelRunner(runner).run("pull", model="ai/model", yes=True)
    assert code == 0 and payload["executed"]

    inventory = RecordingRunner(stdout='{"id":"ai/a"}\n{"id":"ai/b"}\n')
    payload, code = DockerModelRunner(inventory).run("list-runtime-models")
    assert code == 0 and payload["output"] == [{"id": "ai/a"}, {"id": "ai/b"}]


def test_kubernetes_family_is_deterministic_linked_and_render_only() -> None:
    stack = {
        "name": "demo_stack",
        "runtime": "docker_model_runner",
        "model": "local-chat",
        "endpoint": "http://localhost:12434",
    }
    first = render_kubernetes(stack, image="registry.example/runtime:reviewed", device_class="gpu.example.com")
    assert first == render_kubernetes(stack, image="registry.example/runtime:reviewed", device_class="gpu.example.com")
    assert set(first["files"]) == {"resourceclaim.yaml", "deployment.yaml", "service.yaml", "values.yaml"}
    assert first["apply_supported"] is False
    assert "resource.k8s.io/v1" in first["files"]["resourceclaim.yaml"]
    assert "resourceClaimName: demo-stack-accelerator" in first["files"]["deployment.yaml"]
    assert "kind: Service" in first["files"]["service.yaml"]
    assert "secret" not in json.dumps(first).lower()


@pytest.mark.parametrize(("field", "value"), [("image", ""), ("device_class", ""), ("namespace", "Bad Namespace")])
def test_kubernetes_family_rejects_incomplete_inputs(field: str, value: str) -> None:
    kwargs = {"image": "example/runtime:tag", "device_class": "gpu.example.com", "namespace": "default"}
    kwargs[field] = value
    with pytest.raises(ValueError):
        render_kubernetes({"name": "demo", "model": "m", "runtime": "r", "endpoint": "http://x:8000"}, **kwargs)
