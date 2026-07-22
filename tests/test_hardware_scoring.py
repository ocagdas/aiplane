from __future__ import annotations

import json
import subprocess

import pytest

from aiplane.hardware_discovery import discover_hardware
from aiplane.placement import assess_placement, estimate_resources
from aiplane.platform_support import HostPlatform
from aiplane.scoring import score_model, scoring_profiles


class FakeRunner:
    def __init__(self, outputs: dict[tuple[str, ...], str]):
        self.outputs = outputs
        self.commands: list[list[str]] = []

    def run(self, command: list[str], **kwargs):
        self.commands.append(command)
        output = self.outputs.get(tuple(command))
        return subprocess.CompletedProcess(command, 0 if output is not None else 1, output or "", "")


def test_nvidia_discovery_preserves_devices_groups_free_memory_and_topology(monkeypatch) -> None:
    query = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,memory.free,uuid,pci.bus_id,compute_cap,driver_version",
        "--format=csv,noheader,nounits",
    ]
    runner = FakeRunner(
        {
            tuple(query): (
                "0, RTX 6000 Ada, 49140, 45000, GPU-a, 0000:01:00.0, 8.9, 555.42\n"
                "1, RTX 6000 Ada, 49140, 44000, GPU-b, 0000:02:00.0, 8.9, 555.42"
            ),
            ("nvidia-smi", "topo", "-m"): "        GPU0 GPU1\nGPU0   X NV4\nGPU1 NV4 X",
        }
    )
    monkeypatch.setattr(
        "aiplane.hardware_discovery.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "nvidia-smi" else None,
    )

    found = discover_hardware(runner, HostPlatform("Linux", "ubuntu", ("debian",), "x86_64"))

    assert [gpu["device_id"] for gpu in found["gpus"]] == ["GPU-a", "GPU-b"]
    assert found["gpus"][0]["free_vram_gb"] == pytest.approx(43.95, abs=0.01)
    assert found["gpu_groups"][0]["count"] == 2
    assert found["gpu_groups"][0]["total_vram_gb"] == pytest.approx(95.98, abs=0.01)
    assert found["topology"]["state"] == "detected"
    assert any(link["connection"] == "NV4" for link in found["topology"]["links"])


def test_apple_and_windows_discovery_use_platform_specific_sources() -> None:
    apple = FakeRunner(
        {
            ("sysctl", "-n", "hw.memsize"): str(64 * 1024**3),
            ("system_profiler", "SPDisplaysDataType", "-json"): json.dumps(
                {"SPDisplaysDataType": [{"sppci_model": "Apple M4 Max"}]}
            ),
        }
    )
    apple_found = discover_hardware(apple, HostPlatform("Darwin", None, (), "arm64"))
    assert apple_found["memory"]["architecture"] == "unified"
    assert apple_found["gpus"][0]["backend"] == "metal"
    assert apple_found["gpus"][0]["unified_memory"] is True

    powershell_payload = {
        "memory": {"total_kib": 32 * 1024**2, "available_kib": 20 * 1024**2},
        "gpus": [
            {
                "Name": "NVIDIA RTX 4090",
                "AdapterRAM": 24 * 1024**3,
                "PNPDeviceID": "PCI\\GPU0",
                "DriverVersion": "1.2",
            }
        ],
    }

    class WindowsRunner(FakeRunner):
        def run(self, command: list[str], **kwargs):
            self.commands.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(powershell_payload), "")

    windows_found = discover_hardware(WindowsRunner({}), HostPlatform("Windows", None, (), "AMD64"))
    assert windows_found["available_memory_gb"] == 20
    assert windows_found["gpus"][0]["vendor"] == "nvidia"
    assert windows_found["gpus"][0]["source"] == "Win32_VideoController"


def test_resource_estimate_uses_exact_kv_formula_when_architecture_is_known() -> None:
    model = {
        "model": "example-7b-q4",
        "quantization": "q4",
        "architecture": {
            "num_hidden_layers": 32,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
            "hidden_size": 4096,
        },
    }
    estimate = estimate_resources(model, context_tokens=32768)

    assert estimate["weight_source"] == "estimated_from_parameters_and_quantization"
    assert estimate["kv_cache_source"] == "architecture_formula_v1"
    assert estimate["kv_cache_gb"] == pytest.approx(4.0)
    assert estimate["estimated_total_gb"] > estimate["weight_size_gb"]


def _machine(devices: list[dict[str, object]], ram: float = 64) -> dict[str, object]:
    return {
        "memory": {"ram_gb": ram},
        "gpu": {
            "vendor": devices[0]["vendor"] if devices else "none",
            "count": len(devices),
            "devices": devices,
        },
    }


def test_multi_gpu_placement_never_combines_heterogeneous_devices() -> None:
    model = {"model": "example-30b-q4", "weight_size_gb": 20, "runtime_overhead_gb": 1}
    devices = [
        {"index": 0, "vendor": "nvidia", "name": "A", "backend": "cuda", "vram_gb": 16},
        {"index": 1, "vendor": "nvidia", "name": "B", "backend": "cuda", "vram_gb": 16},
    ]

    assessment = assess_placement(model, _machine(devices, ram=16), runtime="vllm", context_tokens=4096)
    tensor = next(mode for mode in assessment["modes"] if mode["mode"] == "tensor_parallel")

    assert tensor["feasible"] is False
    assert "homogeneous" in " ".join(tensor["blockers"])
    assert assessment["eligible"] is False


def test_homogeneous_multi_gpu_placement_checks_attention_head_divisibility() -> None:
    devices = [
        {"index": 0, "vendor": "nvidia", "name": "A", "backend": "cuda", "vram_gb": 16},
        {"index": 1, "vendor": "nvidia", "name": "A", "backend": "cuda", "vram_gb": 16},
    ]
    divisible = {
        "model": "example",
        "weight_size_gb": 20,
        "runtime_overhead_gb": 1,
        "architecture": {"num_attention_heads": 32},
    }
    blocked = {**divisible, "architecture": {"num_attention_heads": 33}}

    assert assess_placement(divisible, _machine(devices, ram=16), runtime="vllm")["selected_mode"] == "tensor_parallel"
    result = assess_placement(blocked, _machine(devices, ram=16), runtime="vllm")
    tensor = next(mode for mode in result["modes"] if mode["mode"] == "tensor_parallel")
    assert tensor["feasible"] is False
    assert "not divisible" in " ".join(tensor["blockers"])


def test_scoring_separates_eligibility_reports_coverage_and_ignores_untyped_smoke() -> None:
    placement = {
        "eligible": True,
        "selected_mode": "single_gpu",
        "resources": {
            "estimated_total_gb": 8,
            "native_context_tokens": 32768,
            "context_tokens": 8192,
            "confidence": "medium",
        },
        "modes": [{"mode": "single_gpu", "available_gb": 16, "feasible": True}],
    }
    model = {"capabilities": {"scores": {"coding": 4, "chat": 5}}}
    score = score_model(
        model,
        placement,
        {"compatibility_score": 0.8},
        benchmark={"summary": {"average_score": 99, "average_elapsed_ms": 10}},
    )

    assert 0 < score["selection_score"] <= 100
    assert score["coverage"] < 1
    assert score["components"]["measured_quality"]["value"] is None
    assert score["components"]["measured_performance"]["value"] is None
    assert score["components"]["task_suitability"]["source"] == "configured"

    ineligible = score_model(model, {**placement, "eligible": False}, {"compatibility_score": 1})
    assert ineligible["selection_score"] == 0


def test_data_only_scoring_extension_is_explicit_and_weighted() -> None:
    config = {
        "placement_scoring": {
            "default_profile": "balanced",
            "extensions": [
                {
                    "name": "team_validation",
                    "source_key": "team_validation",
                    "weight": 0.2,
                    "description": "reviewed internal evaluation",
                }
            ],
        }
    }
    model = {
        "capabilities": {"scores": {"coding": 4}},
        "score_contributions": {
            "team_validation": {
                "value": 92,
                "source": "reviewed_eval_v2",
                "basis": "fixed internal suite",
            }
        },
    }
    placement = {
        "eligible": True,
        "selected_mode": "cpu_only",
        "resources": {"estimated_total_gb": 2, "context_tokens": 4096, "confidence": "high"},
        "modes": [{"mode": "cpu_only", "available_gb": 8, "feasible": True}],
    }
    definitions = scoring_profiles(config)
    score = score_model(model, placement, {"compatibility_score": 1}, config=config)

    assert definitions["extensions"][0]["source_key"] == "team_validation"
    assert score["components"]["team_validation"]["value"] == 92
    assert score["components"]["team_validation"]["source"] == "reviewed_eval_v2"
    assert any(item["component"] == "team_validation" for item in score["contributions"])


@pytest.mark.parametrize(
    "bad",
    [
        {"placement_scoring": {"profiles": {"bad": {"weights": {"fit": -0.1}}}}},
        {"placement_scoring": {"extensions": [{"name": "x", "source_key": "x", "weight": 2}]}},
    ],
)
def test_invalid_scoring_configuration_is_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        scoring_profiles(bad)
