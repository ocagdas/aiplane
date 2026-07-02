from __future__ import annotations

from argparse import Namespace
from typing import Any, Mapping

from .model_catalog import expand_capability_filters


MODEL_SORT_CHOICES = ["name", "avg", "role", "benchmark", "likes", "downloads", "popularity", "parameters"]
GPU_VENDOR_CHOICES = ["generic", "none", "cpu", "nvidia", "amd", "apple", "intel", "mixed"]
ACCELERATOR_API_CHOICES = ["any", "generic", "cpu", "cuda", "rocm", "metal", "vulkan", "openvino"]

MODEL_FILTER_SCHEMA_PROPERTIES: dict[str, dict[str, Any]] = {
    "capabilities": {
        "type": "object",
        "additionalProperties": {"type": "number"},
        "description": "Capability thresholds, for example {code_generation: 4, debugging_refactor: 3}",
    },
    "capability": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Alternative string filters, for example code_generation>=4 or debugging>=3",
    },
    "provider": {"type": "string"},
    "runtime": {"type": "string"},
    "source": {"type": "string"},
    "role": {"type": "array", "items": {"type": "string"}},
    "ownership": {"type": "string", "enum": ["self_managed", "managed_service"]},
    "enabled_only": {"type": "boolean", "default": False},
    "ram_gb": {"type": "number"},
    "vram_gb": {"type": "number"},
    "min_parameters_b": {"type": "number"},
    "max_parameters_b": {"type": "number"},
    "gpu_vendor": {"type": "string", "enum": GPU_VENDOR_CHOICES},
    "accelerator_api": {"type": "string", "enum": ACCELERATOR_API_CHOICES},
    "min_capability_avg_score": {"type": "number"},
    "score_source": {"type": "string"},
    "min_benchmark_score": {"type": "number"},
    "require_benchmark": {"type": "boolean", "default": False},
    "min_likes": {"type": "number"},
    "min_downloads": {"type": "number"},
}


def model_filter_args(values: Namespace | Mapping[str, Any]) -> dict[str, object]:
    ownership = _value(values, "ownership")
    if _bool_value(values, "self_managed_only"):
        ownership = "self_managed"
    if _bool_value(values, "managed_service_only"):
        ownership = "managed_service"

    capabilities = expand_capability_filters(_list_value(values, "capability"))
    for name, threshold in _dict_value(values, "capabilities").items():
        try:
            capabilities[str(name)] = int(threshold)
        except (TypeError, ValueError):
            continue

    return {
        "provider": _value(values, "provider"),
        "runtime": _value(values, "runtime"),
        "source": _value(values, "source"),
        "roles": _list_value(values, "role"),
        "enabled_only": _bool_value(values, "enabled_only"),
        "ownership": ownership,
        "capabilities": capabilities,
        "min_capability_avg_score": _value(values, "min_capability_avg_score"),
        "score_source": _value(values, "score_source"),
        "min_benchmark_score": _value(values, "min_benchmark_score"),
        "require_benchmark": _bool_value(values, "require_benchmark"),
        "min_likes": _value(values, "min_likes"),
        "min_downloads": _value(values, "min_downloads"),
        "max_min_ram_gb": _value(values, "ram_gb"),
        "max_min_vram_gb": _value(values, "vram_gb"),
        "min_parameters_b": _value(values, "min_parameters_b"),
        "max_parameters_b": _value(values, "max_parameters_b"),
        "gpu_vendor": _value(values, "gpu_vendor"),
        "accelerator_api": _value(values, "accelerator_api"),
    }


def _value(values: Namespace | Mapping[str, Any], name: str) -> Any:
    if isinstance(values, Mapping):
        return values.get(name)
    return getattr(values, name, None)


def _bool_value(values: Namespace | Mapping[str, Any], name: str) -> bool:
    return bool(_value(values, name))


def _list_value(values: Namespace | Mapping[str, Any], name: str) -> list[str]:
    value = _value(values, name)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _dict_value(values: Namespace | Mapping[str, Any], name: str) -> dict[str, Any]:
    value = _value(values, name)
    return value if isinstance(value, dict) else {}
