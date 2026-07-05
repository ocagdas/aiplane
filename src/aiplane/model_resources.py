from __future__ import annotations

import re
from typing import Any


def parameter_billions(model_id: str) -> float:
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*b", model_id, flags=re.IGNORECASE)
    if not matches:
        return 0.0
    try:
        return float(matches[-1])
    except ValueError:
        return 0.0


def size_bonus(params: float) -> int:
    if params >= 70:
        return 3
    if params >= 30:
        return 3
    if params >= 14:
        return 2
    if params >= 7:
        return 1
    return 0


def resource_estimate_source(model: dict[str, Any]) -> str | None:
    source = model.get("resource_estimate_source")
    if source:
        return str(source)
    if any(
        key in model
        for key in [
            "min_ram_gb",
            "recommended_ram_gb",
            "min_vram_gb",
            "recommended_vram_gb",
        ]
    ):
        return "configured"
    return None


def gpu_vendor_requirement(model: dict[str, Any]) -> str:
    for key in ["required_gpu_vendor", "gpu_vendor_requirement", "gpu_vendor"]:
        value = str(model.get(key) or "").strip().lower()
        if value:
            if value == "any":
                return "generic"
            return value
    return "generic"


def accelerator_api_requirements(model: dict[str, Any]) -> list[str]:
    for key in [
        "required_accelerator_apis",
        "accelerator_api_requirements",
        "accelerator_apis",
    ]:
        values = _string_list(model.get(key))
        if values:
            return [value.lower() for value in values]
    return []


def matches_gpu_vendor_requirement(
    model: dict[str, Any], available_vendor: str
) -> bool:
    available = available_vendor.strip().lower()
    requirement = gpu_vendor_requirement(model)
    if available in {"", "any", "generic"}:
        return requirement in {"generic", "none", "cpu"}
    if requirement in {"generic", "none", "cpu"}:
        return True
    if requirement == "mixed":
        return available not in {"none", "cpu"}
    return requirement == available


def matches_accelerator_api_requirement(
    model: dict[str, Any], available_api: str
) -> bool:
    available = available_api.strip().lower()
    requirements = accelerator_api_requirements(model)
    if not requirements:
        return True
    if available in {"", "any", "generic"}:
        return False
    return available in requirements


def resource_guess(params: float, roles: list[str]) -> tuple[int, int, int, int | None]:
    if "embedding" in roles:
        return 4, 8, 0, None
    if "text_to_speech" in roles:
        return 8, 16, 0, None
    if "speech_to_text" in roles:
        return 16, 32, 0, 8
    if "image_generation" in roles:
        return 32, 64, 12, 16
    if "video_generation" in roles:
        return 64, 128, 8, 16
    if params <= 0:
        return 8, 16, 0, None
    if params <= 2:
        return 8, 16, 0, None
    if params <= 4:
        return 12, 24, 0, 4
    if params <= 9:
        return 16, 32, 6, 10
    if params <= 16:
        return 32, 64, 12, 16
    if params <= 35:
        return 64, 128, 24, 32
    return 128, 256, 48, 80


def number_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    text = str(value)
    return [text] if text else []
