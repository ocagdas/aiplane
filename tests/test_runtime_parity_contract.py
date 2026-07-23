from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aiplane.backends import BackendResult, OllamaBackend, OpenAICompatibleBackend
from aiplane.benchmarks import BenchmarkRunner
from aiplane.cli import main as cli_main
from aiplane.config import load_profile
from aiplane.runtime_catalog import RuntimeCatalog
from aiplane.runtime_parity import PARITY_RUNTIMES, capability_matrix


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
