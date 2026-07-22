from __future__ import annotations

from typing import Any

from .materialized_catalog import property_matches, public_catalog_row
from .model_resources import (
    matches_accelerator_api_requirement,
    matches_gpu_vendor_requirement,
    number_or_none,
)


def filter_catalog_rows(rows: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    capability_filters = filters.get("capabilities") or {}
    property_filters = filters.get("properties") if isinstance(filters.get("properties"), dict) else {}
    result = []
    for row in rows:
        if filters.get("name") and row.get("name") != filters["name"]:
            continue
        if filters.get("model") and row.get("model") != filters["model"]:
            continue
        if filters.get("provider") and row.get("provider") != filters["provider"]:
            continue
        if filters.get("source") and row.get("source") != filters["source"]:
            continue
        if filters.get("runtime") and filters["runtime"] not in row.get("supported_runtimes", []):
            continue
        roles = _string_list(filters.get("roles") or filters.get("role"))
        if roles and not any(role in row.get("roles", []) for role in roles):
            continue
        if filters.get("enabled_only") and not row.get("enabled"):
            continue
        if filters.get("ownership") and row.get("ownership") != filters["ownership"]:
            continue
        score_source = filters.get("score_source")
        if score_source and row.get("capabilities", {}).get("score_source") != score_source:
            continue
        minimum_average = filters.get("min_capability_avg_score")
        if minimum_average is not None and float(row.get("capability_avg_score", 0)) < float(minimum_average):
            continue
        benchmark = row.get("latest_benchmark") if isinstance(row.get("latest_benchmark"), dict) else None
        minimum_benchmark = filters.get("min_benchmark_score")
        if minimum_benchmark is not None:
            if not benchmark or float(benchmark.get("average_score", 0)) < float(minimum_benchmark):
                continue
        if filters.get("require_benchmark") and not benchmark:
            continue
        if filters.get("min_likes") is not None and float(row.get("likes") or 0) < float(filters["min_likes"]):
            continue
        if filters.get("min_downloads") is not None and float(row.get("downloads") or 0) < float(
            filters["min_downloads"]
        ):
            continue
        scores = row.get("capabilities", {}).get("scores", {})
        if any(int(scores.get(name, 0)) < minimum for name, minimum in capability_filters.items()):
            continue
        required_ram = number_or_none(row.get("min_ram_gb"))
        if (
            filters.get("max_min_ram_gb") is not None
            and required_ram
            and required_ram > float(filters["max_min_ram_gb"])
        ):
            continue
        required_vram = number_or_none(row.get("min_vram_gb"))
        if (
            filters.get("max_min_vram_gb") is not None
            and required_vram
            and required_vram > float(filters["max_min_vram_gb"])
        ):
            continue
        parameters = float(row.get("parameter_count_b") or 0)
        if filters.get("min_parameters_b") is not None and parameters < float(filters["min_parameters_b"]):
            continue
        if filters.get("max_parameters_b") is not None and (
            parameters <= 0 or parameters > float(filters["max_parameters_b"])
        ):
            continue
        if filters.get("gpu_vendor") and not matches_gpu_vendor_requirement(row, str(filters["gpu_vendor"])):
            continue
        if filters.get("accelerator_api") and not matches_accelerator_api_requirement(
            row, str(filters["accelerator_api"])
        ):
            continue
        properties = row.get("_properties") if isinstance(row.get("_properties"), dict) else {}
        if any(not property_matches(properties, str(name), expected) for name, expected in property_filters.items()):
            continue
        result.append(public_catalog_row(row))
    return sorted(result, key=lambda row: str(row["name"]))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]
