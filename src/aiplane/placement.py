"""Explainable model memory estimates and runtime-aware device placement."""

from __future__ import annotations

import re
from typing import Any

from .model_resources import parameter_billions

SCHEMA_VERSION = "1.0"
MULTI_GPU_RUNTIMES = {
    "vllm": "tensor_parallel",
    "tgi": "tensor_parallel",
    "transformers": "tensor_parallel",
    "ollama": "tensor_split",
    "llamacpp": "tensor_split",
}
OFFLOAD_RUNTIMES = {"ollama", "llamacpp", "localai", "lmstudio"}
BACKEND_BY_RUNTIME = {
    "vllm": {"cuda", "rocm"},
    "tgi": {"cuda", "rocm"},
    "transformers": {"cuda", "rocm", "metal", "openvino"},
    "ollama": {"cuda", "rocm", "metal"},
    "llamacpp": {"cuda", "rocm", "metal", "vulkan"},
    "localai": {"cuda", "rocm", "metal", "vulkan"},
    "lmstudio": {"cuda", "metal", "vulkan"},
}


def assess_placement(
    model: dict[str, Any],
    machine: dict[str, Any],
    *,
    runtime: str | None = None,
    context_tokens: int | None = None,
) -> dict[str, Any]:
    selected_runtime = (runtime or model.get("preferred_runtime") or "").strip().lower() or None
    resources = estimate_resources(model, context_tokens=context_tokens)
    gpu = machine.get("gpu", {}) if isinstance(machine.get("gpu"), dict) else {}
    devices = [item for item in gpu.get("devices", []) if isinstance(item, dict)]
    if not devices and _number(gpu.get("vram_gb")):
        devices = [
            {
                "index": 0,
                "vendor": gpu.get("vendor"),
                "name": gpu.get("model"),
                "backend": _backend_for_vendor(str(gpu.get("vendor") or "")),
                "vram_gb": _number(gpu.get("vram_gb")),
                "free_vram_gb": _number(gpu.get("free_vram_gb")),
                "configured": True,
            }
        ]
    memory = machine.get("memory", {}) if isinstance(machine.get("memory"), dict) else {}
    ram = _number(memory.get("unified_memory_gb")) or _number(memory.get("ram_gb"))
    required = _number(resources.get("estimated_total_gb"))
    modes = _placement_modes(devices, ram, required, selected_runtime, model)
    selected = next((mode for mode in modes if mode["feasible"] is True), None)
    blockers = [] if selected else _deduplicate(reason for mode in modes for reason in mode.get("blockers", []))
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime": selected_runtime,
        "context_tokens": resources["context_tokens"],
        "resources": resources,
        "devices_considered": devices,
        "modes": modes,
        "selected_mode": selected["mode"] if selected else None,
        "eligible": selected is not None,
        "blockers": blockers,
        "important": "VRAM is combined only when the selected runtime and homogeneous device group support model splitting.",
    }


def estimate_resources(model: dict[str, Any], *, context_tokens: int | None = None) -> dict[str, Any]:
    model_id = str(model.get("model") or model.get("name") or "")
    params = (
        _number(model.get("parameter_count_b")) or _number(model.get("parameters_b")) or parameter_billions(model_id)
    )
    bits = _quantization_bits(model)
    assumptions: list[str] = []
    weight_source = "configured"
    weights = _number(model.get("weight_size_gb")) or _number(model.get("artifact_size_gb"))
    if weights is None and params:
        weights = round(params * bits / 8 * 1.10, 2)
        weight_source = "estimated_from_parameters_and_quantization"
        assumptions.append("weight estimate includes 10% format/runtime overhead")
    native_context = _integer(model.get("context_window_tokens") or model.get("context_tokens"))
    resolved_context = context_tokens or min(native_context, 8192) if native_context else context_tokens or 8192
    if context_tokens is None:
        assumptions.append("context defaults to the smaller of the model limit and 8192 tokens")
    kv, kv_source = _kv_cache(model, resolved_context)
    if kv is None:
        configured = _number(model.get("kv_cache_gb"))
        if configured is not None:
            kv, kv_source = configured, "configured"
        else:
            assumptions.append("KV cache is unresolved because model architecture metadata is incomplete")
    overhead = _number(model.get("runtime_overhead_gb"))
    if overhead is None and weights is not None:
        overhead = round(max(0.5, weights * 0.05), 2)
        assumptions.append("runtime workspace estimate is 5% of weights with a 0.5GB floor")
    total = round(weights + (kv or 0) + (overhead or 0), 2) if weights is not None else None
    confidence = (
        "high" if weight_source == "configured" and kv is not None else "medium" if weights is not None else "low"
    )
    return {
        "parameter_count_b": params or None,
        "quantization_bits": bits,
        "context_tokens": resolved_context,
        "native_context_tokens": native_context,
        "weight_size_gb": weights,
        "weight_source": weight_source if weights is not None else "unresolved",
        "kv_cache_gb": kv,
        "kv_cache_source": kv_source,
        "runtime_overhead_gb": overhead,
        "estimated_total_gb": total,
        "confidence": confidence,
        "assumptions": assumptions,
    }


def _placement_modes(
    devices: list[dict[str, Any]],
    ram_gb: float | None,
    required_gb: float | None,
    runtime: str | None,
    model: dict[str, Any],
) -> list[dict[str, Any]]:
    modes: list[dict[str, Any]] = []
    known_runtime = bool(runtime)
    compatible = BACKEND_BY_RUNTIME.get(runtime or "", set())
    usable = [device for device in devices if not compatible or str(device.get("backend") or "") in compatible]
    capacities = [_capacity(device) for device in usable]
    best = max((value for value in capacities if value is not None), default=None)
    single_ok = _fits(required_gb, best)
    modes.append(
        {
            "mode": "single_gpu",
            "feasible": single_ok if usable and required_gb is not None else None,
            "available_gb": best,
            "device_indices": [usable[capacities.index(best)].get("index")] if best is not None else [],
            "blockers": _fit_blockers(required_gb, best, "single GPU") if single_ok is not True else [],
        }
    )

    split_kind = MULTI_GPU_RUNTIMES.get(runtime or "")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for device in usable:
        key = (str(device.get("vendor")), str(device.get("name")), str(device.get("backend")))
        groups.setdefault(key, []).append(device)
    candidates = [members for members in groups.values() if len(members) > 1]
    group = max(candidates, key=lambda members: sum(_capacity(item) or 0 for item in members), default=[])
    total = sum(_capacity(item) or 0 for item in group) if group else None
    split_blockers = []
    if not known_runtime:
        split_blockers.append("select a runtime before evaluating multi-GPU placement")
    elif not split_kind:
        split_blockers.append(f"runtime '{runtime}' has no declared multi-GPU placement contract")
    elif not group:
        split_blockers.append("no homogeneous multi-GPU group with a compatible backend is available")
    heads = _integer(_architecture(model).get("num_attention_heads"))
    if split_kind == "tensor_parallel" and heads and group and heads % len(group):
        split_blockers.append(f"{heads} attention heads are not divisible by {len(group)} devices")
    if required_gb is None:
        split_blockers.append("model memory requirement is unresolved")
    elif total is not None and total < required_gb:
        split_blockers.append(f"{split_kind or 'multi-GPU'} needs {required_gb:g}GB; group has {total:g}GB")
    modes.append(
        {
            "mode": split_kind or "multi_gpu",
            "feasible": False if split_blockers else True,
            "available_gb": round(total, 2) if total is not None else None,
            "device_indices": [item.get("index") for item in group],
            "blockers": split_blockers,
        }
    )

    if runtime in OFFLOAD_RUNTIMES:
        combined = (best or 0) + (ram_gb or 0) * 0.8
        offload_ok = required_gb is not None and combined >= required_gb
        modes.append(
            {
                "mode": "cpu_offload",
                "feasible": offload_ok,
                "available_gb": round(combined, 2),
                "device_indices": [item.get("index") for item in usable[:1]],
                "blockers": [] if offload_ok else _fit_blockers(required_gb, combined, "GPU plus 80% of system memory"),
            }
        )

    cpu_ok = required_gb is not None and ram_gb is not None and ram_gb * 0.8 >= required_gb
    modes.append(
        {
            "mode": "cpu_only",
            "feasible": cpu_ok,
            "available_gb": round(ram_gb * 0.8, 2) if ram_gb is not None else None,
            "device_indices": [],
            "blockers": []
            if cpu_ok
            else _fit_blockers(required_gb, ram_gb * 0.8 if ram_gb else None, "80% of system memory"),
        }
    )
    return modes


def _kv_cache(model: dict[str, Any], context: int) -> tuple[float | None, str]:
    architecture = _architecture(model)
    layers = _integer(architecture.get("num_hidden_layers") or architecture.get("layers"))
    attention_heads = _integer(architecture.get("num_attention_heads") or architecture.get("attention_heads"))
    kv_heads = _integer(architecture.get("num_key_value_heads") or architecture.get("kv_heads")) or attention_heads
    head_dim = _integer(architecture.get("head_dim"))
    hidden = _integer(architecture.get("hidden_size"))
    if head_dim is None and hidden and attention_heads:
        head_dim = hidden // attention_heads
    dtype_bytes = _number(model.get("kv_cache_dtype_bytes")) or 2
    if not all((layers, kv_heads, head_dim)):
        return None, "unresolved"
    size = 2 * layers * kv_heads * head_dim * context * dtype_bytes / 1024**3
    return round(size, 3), "architecture_formula_v1"


def _architecture(model: dict[str, Any]) -> dict[str, Any]:
    architecture = model.get("architecture")
    return architecture if isinstance(architecture, dict) else model


def _quantization_bits(model: dict[str, Any]) -> float:
    explicit = _number(model.get("quantization_bits"))
    if explicit:
        return explicit
    text = str(model.get("quantization") or model.get("quantization_level") or model.get("model") or "")
    match = re.search(r"(?:^|[-_:])q(\d+)", text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else 16.0


def _capacity(device: dict[str, Any]) -> float | None:
    free = _number(device.get("free_vram_gb"))
    total = _number(device.get("vram_gb"))
    return free if free is not None else round(total * 0.9, 2) if total is not None else None


def _fits(required: float | None, available: float | None) -> bool | None:
    return None if required is None or available is None else available >= required


def _fit_blockers(required: float | None, available: float | None, label: str) -> list[str]:
    if required is None:
        return ["model memory requirement is unresolved"]
    if available is None:
        return [f"{label} memory is unresolved"]
    return [f"{label} needs {required:g}GB; {available:g}GB is available"]


def _backend_for_vendor(vendor: str) -> str:
    return {"nvidia": "cuda", "amd": "rocm", "apple": "metal", "intel": "openvino"}.get(vendor, "unknown")


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _deduplicate(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
