from __future__ import annotations

import copy
import json
import re
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from aiplane.artifact_validation import validate_runtime_bundle
from aiplane.backends import BackendResult, OllamaBackend, OpenAICompatibleBackend
from aiplane.benchmarks import BenchmarkRunner
from aiplane.cli import main as cli_main
from aiplane.config import load_profile
from aiplane.runtime_catalog import RuntimeCatalog
from aiplane.runtime_definitions import PROVIDER_ENDPOINT_DEFAULTS
from aiplane.runtime_parity import PARITY_RUNTIMES, capability_matrix
from aiplane.runtime_specs import PRIMARY_RUNTIME_SPECS

from .runtime_fixtures import PRIMARY_RUNTIME_FIXTURES, catalog_for_runtime_fixture


def test_primary_runtime_capability_contract_is_complete() -> None:
    payload = capability_matrix()
    assert tuple(payload["runtimes"]) == PARITY_RUNTIMES
    required = {"detection", "inventory", "identity_mapping", "fit", "health", "endpoint_export", "lifecycle"}
    assert all(set(row) == required for row in payload["runtimes"].values())
    assert all(item["state"] in payload["states"] for row in payload["runtimes"].values() for item in row.values())


def test_capabilities_cli_and_mlx_plan_are_machine_readable() -> None:
    output = StringIO()
    with redirect_stdout(output):
        assert cli_main(["runtimes", "capabilities", "mlx"]) == 0
    assert list(json.loads(output.getvalue())["runtimes"]) == ["mlx"]

    output = StringIO()
    with redirect_stdout(output):
        assert cli_main(["runtimes", "install", "mlx", "--dry-run"]) == 0
    planned = json.loads(output.getvalue())
    assert planned["execution"] == "planned_only"
    assert planned["command"][-1] == "mlx-lm"


def test_mlx_and_vllm_launch_manifests_use_current_entrypoints() -> None:
    profile = load_profile("local-dev", Path.cwd())
    catalog = RuntimeCatalog(profile)
    mlx_model = dict(profile.models["models"]["provider-code-large-vllm"])
    mlx_model["supported_runtimes"] = ["mlx", "vllm"]
    profile.models["models"]["provider-code-large-vllm"] = mlx_model
    mlx = catalog.launch_manifest("mlx", "provider-code-large-vllm")
    vllm = catalog.launch_manifest("vllm", "provider-code-large-vllm")
    assert mlx["launch"]["command"][:3] == ["python", "-m", "mlx_lm.server"]
    assert vllm["launch"]["command"][:2] == ["vllm", "serve"]
    assert mlx["endpoint"]["health_path"] == "/v1/models"
    assert mlx["launch"]["environment"] == {}


def test_benchmark_prefers_runtime_native_measurements() -> None:
    profile = load_profile("local-dev", Path.cwd())
    runner = BenchmarkRunner(profile)
    native = BackendResult(
        "ollama",
        "add returns a sum and an edge case is mixed types",
        False,
        {
            "elapsed_ms": 12.5,
            "ttft_ms": 3.5,
            "prompt_tokens": 10,
            "output_tokens": 8,
            "tokens_per_second": 20.0,
            "source": "fixture_native",
        },
    )
    with patch.object(runner.catalog, "complete", return_value=native):
        result = runner.run("fixture-analysis-small", save=False)
    row = result["results"][0]
    assert row["elapsed_ms"] == 12.5
    assert row["ttft_ms"] == 3.5
    assert row["prompt_tokens"] == 10
    assert row["output_tokens"] == 8
    assert row["tokens_per_second"] == 20.0
    assert row["telemetry_source"] == "fixture_native"
    assert result["runtime_evidence"]["artifact_lock"]["record_type"] == "model_artifact_lock"


class _JsonResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self._payload


class _JsonTransport:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def open(self, request, timeout=None):
        return _JsonResponse(self.payload)


def test_ollama_backend_preserves_native_token_and_duration_fields() -> None:
    backend = OllamaBackend(
        http_transport=_JsonTransport(
            {
                "message": {"content": "ok"},
                "prompt_eval_count": 12,
                "eval_count": 8,
                "eval_duration": 400_000_000,
                "total_duration": 750_000_000,
            }
        )
    )
    result = backend.chat("model", "hello")
    assert result.telemetry == {
        "elapsed_ms": 750.0,
        "ttft_ms": None,
        "prompt_tokens": 12,
        "output_tokens": 8,
        "tokens_per_second": 20.0,
        "source": "ollama_native_response",
    }


def test_openai_compatible_backend_preserves_zero_completion_tokens() -> None:
    backend = OpenAICompatibleBackend(
        "http://localhost:8000/v1",
        http_transport=_JsonTransport(
            {
                "choices": [{"message": {"content": ""}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 0},
            }
        ),
    )
    result = backend.chat("model", "hello")
    assert result.telemetry["prompt_tokens"] == 3
    assert result.telemetry["output_tokens"] == 0


@pytest.mark.parametrize(("runtime", "fixture"), sorted(PRIMARY_RUNTIME_FIXTURES.items()))
def test_realistic_primary_runner_fixture_compiles_consistent_artifacts(
    runtime: str, fixture: dict[str, object]
) -> None:
    catalog, alias, fixture = catalog_for_runtime_fixture(runtime)
    model_id = str(fixture["model"])
    profile = catalog.profile
    spec = PRIMARY_RUNTIME_SPECS[runtime]

    assert catalog.supported_runtimes(alias, include_gui=True) == [runtime]
    assert catalog.source_for_model(profile.models["models"][alias]) == fixture["source"]

    launch = catalog.launch_manifest(runtime, alias)
    assert launch == catalog.launch_manifest(runtime, alias)
    assert launch["launch"]["command"][: len(fixture["launch_prefix"])] == fixture["launch_prefix"]
    assert launch["launch"]["port"] == spec.port
    assert launch["endpoint"] == {
        "base_url": spec.endpoint("127.0.0.1"),
        "health_path": spec.health_path,
        "protocol": spec.protocol,
    }
    assert launch["artifact"]["identity"]["model_id"] == model_id
    assert launch["artifact"]["identity"]["format"] == fixture["format"]

    options = dict(fixture["bundle_options"])
    bundle = catalog.bundle_plan(runtime, alias, **options)
    assert bundle == catalog.bundle_plan(runtime, alias, **options)
    assert bundle["mode"] == fixture["mode"]
    assert bundle["selected_file"] == fixture["selected_file"]
    assert bundle["supported_modes"] == list(spec.bundle_modes)
    if fixture["mode"] == "docker":
        assert bundle["settings"]["container_port"] == spec.container_port
        assert f"-p {spec.port}:{spec.container_port}" in bundle["commands"][1]
    else:
        assert bundle["settings"]["container_port"] is None
    assert fixture["artifact_marker"] in bundle["files"][bundle["selected_file"]]
    assert validate_runtime_bundle(bundle) is bundle
    rendered_commands = "\n".join(bundle["commands"])
    for marker in fixture["command_markers"]:
        assert marker in rendered_commands
    assert "secret-value" not in json.dumps(bundle)


def test_six_runner_bundle_modes_are_truthful_and_reproducible() -> None:
    profile = load_profile("local-dev", Path.cwd())
    alias = "provider-code-large-vllm"
    model = dict(profile.models["models"][alias])
    model["supported_runtimes"] = list(PARITY_RUNTIMES)
    profile.models["models"][alias] = model
    catalog = RuntimeCatalog(profile)
    expected = {
        "ollama": "docker",
        "vllm": "docker",
        "llamacpp": "native",
        "mlx": "conda",
        "docker_model_runner": "native",
        "lmstudio": "native",
    }
    for runtime, mode in expected.items():
        first = catalog.bundle_plan(runtime, alias, mode="auto")
        second = catalog.bundle_plan(runtime, alias, mode="auto")
        assert first == second
        assert first["mode"] == mode
        assert first["selected_file"] in first["files"]
        assert set(first["checksums"]) == set(first["files"])
        if mode == "native":
            assert len(first["commands"]) == 1
            assert not first["commands"][0].startswith("review ")
            assert any("Review runtime-launch.json" in note for note in first["notes"])
    assert "Dockerfile" not in catalog.bundle_plan("mlx", alias, mode="auto")["files"]
    assert set(catalog.bundle_plan("docker_model_runner", alias)["files"]) == {"runtime-launch.json"}


def test_six_runner_bundle_rejects_misleading_substrates() -> None:
    profile = load_profile("local-dev", Path.cwd())
    alias = "provider-code-large-vllm"
    model = dict(profile.models["models"][alias])
    model["supported_runtimes"] = ["mlx", "docker_model_runner", "lmstudio"]
    profile.models["models"][alias] = model
    catalog = RuntimeCatalog(profile)
    for runtime in ["mlx", "docker_model_runner", "lmstudio"]:
        try:
            catalog.bundle_plan(runtime, alias, mode="docker")
        except ValueError as exc:
            assert "does not support" in str(exc)
        else:
            raise AssertionError(f"{runtime} unexpectedly emitted a Docker bundle")


def _catalog_supporting_all_primary_runtimes() -> tuple[RuntimeCatalog, str]:
    profile = load_profile("local-dev", Path.cwd())
    alias = "provider-code-large-vllm"
    model = dict(profile.models["models"][alias])
    model["supported_runtimes"] = list(PARITY_RUNTIMES)
    profile.models["models"][alias] = model
    return RuntimeCatalog(profile), alias


def test_primary_runtime_specs_drive_provider_launch_bundle_and_capability_endpoints() -> None:
    catalog, alias = _catalog_supporting_all_primary_runtimes()
    capabilities = capability_matrix()["runtimes"]
    for runtime, spec in PRIMARY_RUNTIME_SPECS.items():
        assert PROVIDER_ENDPOINT_DEFAULTS[runtime]["endpoint"] == spec.endpoint()
        assert PROVIDER_ENDPOINT_DEFAULTS[runtime]["protocol"] == spec.protocol
        assert PROVIDER_ENDPOINT_DEFAULTS[runtime]["substrate"] == spec.substrate
        assert capabilities[runtime]["endpoint_export"]["interface"] == spec.endpoint()
        launch = catalog.launch_manifest(runtime, alias)
        assert launch["launch"]["port"] == spec.port
        assert launch["endpoint"] == {
            "base_url": spec.endpoint("127.0.0.1"),
            "health_path": spec.health_path,
            "protocol": spec.protocol,
        }
        bundle = catalog.bundle_plan(runtime, alias)
        assert bundle["settings"]["port"] == spec.port
        assert bundle["supported_modes"] == list(spec.bundle_modes)


@pytest.mark.parametrize(
    ("runtime", "mode", "option", "value"),
    [
        ("mlx", "conda", "gpu_devices", ["0"]),
        ("docker_model_runner", "native", "auth_env", "MODEL_TOKEN"),
        ("lmstudio", "native", "environment", ["MODEL_HOME"]),
        ("ollama", "native", "context_tokens", 4096),
        ("vllm", "conda", "cache_volume", "model-cache"),
        ("llamacpp", "native", "tensor_parallel", 2),
    ],
)
def test_bundle_rejects_settings_the_selected_runtime_mode_cannot_apply(
    runtime: str, mode: str, option: str, value: object
) -> None:
    catalog, alias = _catalog_supporting_all_primary_runtimes()
    with pytest.raises(ValueError, match=rf"unsupported.*{option}"):
        catalog.bundle_plan(runtime, alias, mode=mode, **{option: value})


def test_llamacpp_docker_placeholder_is_not_a_supported_bundle() -> None:
    catalog, alias = _catalog_supporting_all_primary_runtimes()
    with pytest.raises(ValueError, match="does not support.*docker"):
        catalog.bundle_plan("llamacpp", alias, mode="docker")


def test_docker_image_names_are_safe_collision_resistant_and_keep_alias_metadata() -> None:
    profile = load_profile("local-dev", Path.cwd())
    template = dict(profile.models["models"]["provider-code-large-vllm"])
    aliases = ["My Model:Alias", "my-model-alias", "X" * 300]
    images = []
    for alias in aliases:
        profile.models["models"][alias] = dict(template)
        plan = RuntimeCatalog(profile).bundle_plan("vllm", alias, mode="docker")
        assert plan["model"] == alias
        assert re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*:local", plan["image"])
        assert plan["image"] in plan["commands"][0]
        assert len(plan["image"]) < 255
        images.append(plan["image"])
    assert len(set(images)) == len(images)


def test_runtime_bundle_application_validation_rejects_cross_field_drift() -> None:
    catalog, alias = _catalog_supporting_all_primary_runtimes()
    payload = catalog.bundle_plan("vllm", alias, mode="docker")
    assert validate_runtime_bundle(payload) is payload

    missing_selected = copy.deepcopy(payload)
    missing_selected["selected_file"] = "missing"
    with pytest.raises(ValueError, match="selected_file"):
        validate_runtime_bundle(missing_selected)

    wrong_checksum = copy.deepcopy(payload)
    wrong_checksum["checksums"]["Dockerfile"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_runtime_bundle(wrong_checksum)

    mismatched_keys = copy.deepcopy(payload)
    mismatched_keys["checksums"]["extra"] = "0" * 64
    with pytest.raises(ValueError, match="keys must match"):
        validate_runtime_bundle(mismatched_keys)


def test_bundle_and_artifact_evidence_use_explicit_reproducibility_levels() -> None:
    catalog, alias = _catalog_supporting_all_primary_runtimes()
    bundle = catalog.bundle_plan("vllm", alias, mode="docker")
    assert bundle["reproducibility"]["level"] == "recipe_deterministic"
    assert bundle["reproducibility"]["version_pinned"] is False
    assert any("latest" in blocker for blocker in bundle["reproducibility"]["blockers"])
    lock = catalog.artifact_lock(alias)
    assert lock["reproducibility"]["level"] == "unresolved"
    assert lock["complete"] is False


def test_managed_service_model_is_not_treated_as_a_local_runtime_pair() -> None:
    profile = load_profile("local-dev", Path.cwd())
    with pytest.raises(ValueError, match="managed-service model.*provider endpoint"):
        RuntimeCatalog(profile).validate_model_runtime("managed-chat-small", "vllm")


def test_profile_runtime_endpoint_override_drives_bundle_and_launch_ports() -> None:
    profile = load_profile("local-dev", Path.cwd())
    profile.models["providers"]["vllm"]["endpoint"] = "http://localhost:9001/v1"
    catalog = RuntimeCatalog(profile)
    bundle = catalog.bundle_plan("vllm", "provider-code-large-vllm", mode="docker")
    launch = catalog.launch_manifest("vllm", "provider-code-large-vllm")
    assert bundle["settings"]["port"] == 9001
    assert bundle["settings"]["container_port"] == 8000
    assert "-p 9001:8000" in bundle["commands"][1]
    assert launch["launch"]["port"] == 9001
    assert launch["endpoint"]["base_url"] == "http://127.0.0.1:9001/v1"
