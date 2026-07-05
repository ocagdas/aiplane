from __future__ import annotations

from pathlib import Path
from typing import Any

from .hardware import HardwareManager
from .machines import MachineManager, load_machine_profile
from .models import Profile


def merge_machine_model_filters(
    profile: Profile,
    filters: dict[str, Any],
    *,
    machine: str | None = None,
    machine_file: Path | None = None,
    current_machine: bool = False,
) -> dict[str, Any]:
    selected = [bool(machine), bool(machine_file), bool(current_machine)]
    if sum(selected) > 1:
        raise ValueError("choose only one of --machine, --machine-file, or --current-machine")
    if not any(selected):
        return filters

    resolved = _resolve_machine(
        profile,
        machine=machine,
        machine_file=machine_file,
        current_machine=current_machine,
    )
    derived = _model_filters_from_machine(resolved)
    merged = dict(filters)
    for key, value in derived.items():
        if merged.get(key) is None and value is not None:
            merged[key] = value
    return merged


def _resolve_machine(
    profile: Profile,
    *,
    machine: str | None,
    machine_file: Path | None,
    current_machine: bool,
) -> dict[str, Any]:
    if machine:
        return MachineManager(profile).show(machine)["machine"]
    if machine_file:
        return load_machine_profile(machine_file)["machine"]
    if current_machine:
        hardware = HardwareManager(profile)
        return hardware.machine(hardware.discover())
    raise ValueError("machine selector is required")


def _model_filters_from_machine(machine: dict[str, Any]) -> dict[str, Any]:
    memory = machine.get("memory") if isinstance(machine.get("memory"), dict) else {}
    gpu = machine.get("gpu") if isinstance(machine.get("gpu"), dict) else {}
    unified_gb = _number(memory.get("unified_memory_gb"))
    ram_gb = _number(memory.get("ram_gb")) or unified_gb
    vram_gb = _number(gpu.get("vram_gb")) or unified_gb
    vendor = _normalized_vendor(gpu.get("vendor"))
    accelerator_api = _preferred_accelerator(machine.get("accelerator_apis"), vendor)
    return {
        "max_min_ram_gb": ram_gb,
        "max_min_vram_gb": vram_gb,
        "gpu_vendor": vendor,
        "accelerator_api": accelerator_api,
    }


def _normalized_vendor(value: Any) -> str | None:
    vendor = str(value or "").strip().lower()
    if not vendor or vendor in {
        "unknown",
        "auto",
        "provider_defined",
        "node_pool_defined",
    }:
        return None
    if vendor in {"none", "cpu"}:
        return "none"
    for candidate in ["nvidia", "amd", "apple", "intel", "mixed"]:
        if candidate in vendor:
            return candidate
    return vendor


def _preferred_accelerator(values: Any, vendor: str | None) -> str | None:
    accelerators = [str(item).strip().lower() for item in values] if isinstance(values, list) else []
    for preferred in ["cuda", "rocm", "metal", "vulkan", "openvino", "cpu"]:
        if preferred in accelerators:
            return preferred
    if vendor == "nvidia":
        return "cuda"
    if vendor == "amd":
        return "rocm"
    if vendor == "apple":
        return "metal"
    if vendor in {"none", "cpu"}:
        return "cpu"
    return None


def _number(value: Any) -> float | None:
    try:
        if value in (None, "", "auto", "provider_defined", "node_pool_defined"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
