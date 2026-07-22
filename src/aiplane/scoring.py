"""Versioned, explainable model placement scoring.

The score describes placement readiness. It deliberately does not claim that
catalog metadata is measured model quality.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_PROFILES: dict[str, dict[str, float]] = {
    "balanced": {
        "resource_fit": 0.30,
        "runtime_readiness": 0.25,
        "context_fit": 0.15,
        "task_suitability": 0.15,
        "measured_performance": 0.10,
        "evidence_confidence": 0.05,
    },
    "quality_evidence": {
        "resource_fit": 0.20,
        "runtime_readiness": 0.15,
        "context_fit": 0.15,
        "task_suitability": 0.20,
        "measured_quality": 0.25,
        "evidence_confidence": 0.05,
    },
    "throughput": {
        "resource_fit": 0.25,
        "runtime_readiness": 0.20,
        "context_fit": 0.10,
        "task_suitability": 0.10,
        "measured_performance": 0.30,
        "evidence_confidence": 0.05,
    },
}


def scoring_profiles(config: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = (config or {}).get("placement_scoring", {})
    configured = raw.get("profiles", {}) if isinstance(raw, dict) else {}
    profiles = {name: dict(weights) for name, weights in DEFAULT_PROFILES.items()}
    if isinstance(configured, dict):
        for name, item in configured.items():
            weights = item.get("weights", item) if isinstance(item, dict) else None
            if isinstance(weights, dict):
                profiles[str(name)] = validate_weights(weights)
    default = str(raw.get("default_profile") or "balanced") if isinstance(raw, dict) else "balanced"
    if default not in profiles:
        raise ValueError(f"unknown default scoring profile: {default}")
    extensions = raw.get("extensions", []) if isinstance(raw, dict) else []
    return {
        "schema_version": SCHEMA_VERSION,
        "default_profile": default,
        "profiles": profiles,
        "extensions": _validate_extensions(extensions),
        "meaning": "placement readiness from available evidence; not a universal model-quality score",
    }


def score_model(
    model: dict[str, Any],
    placement: dict[str, Any],
    runtime_compatibility: dict[str, Any] | None,
    *,
    config: dict[str, Any] | None = None,
    profile_name: str | None = None,
    benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    definitions = scoring_profiles(config)
    selected = profile_name or definitions["default_profile"]
    if selected not in definitions["profiles"]:
        raise ValueError(f"unknown scoring profile: {selected}")
    weights = definitions["profiles"][selected]
    components = _base_components(model, placement, runtime_compatibility, benchmark)
    for extension in definitions["extensions"]:
        contribution = _extension_component(model, extension)
        if contribution:
            components[extension["name"]] = contribution
            weights = dict(weights)
            weights[extension["name"]] = extension["weight"]

    available = {name: item for name, item in components.items() if item.get("value") is not None and name in weights}
    available_weight = sum(float(weights[name]) for name in available)
    contributions = []
    score = 0.0
    for name, component in available.items():
        normalized = float(weights[name]) / available_weight if available_weight else 0.0
        contribution = float(component["value"]) * normalized
        score += contribution
        contributions.append(
            {
                "component": name,
                "value": component["value"],
                "configured_weight": weights[name],
                "normalized_weight": round(normalized, 4),
                "contribution": round(contribution, 2),
            }
        )
    total_weight = sum(float(value) for value in weights.values())
    eligible = bool(placement.get("eligible"))
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": selected,
        "eligible": eligible,
        "selection_score": round(score, 2) if eligible else 0.0,
        "coverage": round(available_weight / total_weight if total_weight else 0.0, 3),
        "components": components,
        "weights": weights,
        "contributions": contributions,
        "method": "weighted arithmetic mean over available evidence; missing components are excluded and reported in coverage",
        "warnings": [
            "Eligibility is a separate hard gate and cannot be outweighed by a high score.",
            "Catalog task suitability is configured metadata, not measured quality.",
        ],
    }


def validate_weights(weights: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for name, value in weights.items():
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"scoring weight '{name}' must be numeric") from exc
        if number < 0 or number > 1:
            raise ValueError(f"scoring weight '{name}' must be between 0 and 1")
        result[str(name)] = number
    if not result or sum(result.values()) <= 0:
        raise ValueError("a scoring profile must contain at least one positive weight")
    return result


def _base_components(
    model: dict[str, Any],
    placement: dict[str, Any],
    runtime: dict[str, Any] | None,
    benchmark: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    resources = placement.get("resources", {}) if isinstance(placement.get("resources"), dict) else {}
    selected = next(
        (item for item in placement.get("modes", []) if item.get("mode") == placement.get("selected_mode")),
        {},
    )
    required = _number(resources.get("estimated_total_gb"))
    available = _number(selected.get("available_gb"))
    resource_fit = None
    if required is not None and available is not None and required > 0:
        headroom = max(0.0, (available - required) / required)
        resource_fit = round(min(100.0, 60.0 + headroom * 40.0), 2)
    runtime_score = _number((runtime or {}).get("compatibility_score"))
    native_context = _number(resources.get("native_context_tokens"))
    requested_context = _number(resources.get("context_tokens"))
    context_fit = None
    if requested_context and native_context:
        context_fit = round(min(100.0, native_context / requested_context * 100.0), 2)
    task_values = _capability_values(model)
    confidence = {"high": 100.0, "medium": 70.0, "low": 35.0}.get(str(resources.get("confidence")), 35.0)
    quality, performance = _typed_benchmark_components(benchmark)
    return {
        "resource_fit": _component(resource_fit, "generated", "placement headroom"),
        "runtime_readiness": _component(
            runtime_score * 100 if runtime_score is not None else None, "detected", "runtime compatibility"
        ),
        "context_fit": _component(context_fit, "configured", "requested versus native context"),
        "task_suitability": _component(
            round(sum(task_values) / len(task_values) * 20, 2) if task_values else None,
            "configured",
            "catalog capability metadata",
        ),
        "measured_quality": quality,
        "measured_performance": performance,
        "evidence_confidence": _component(confidence, "generated", "resource estimate confidence"),
    }


def _typed_benchmark_components(
    benchmark: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(benchmark, dict):
        return (
            _component(None, "unresolved", "no comparable benchmark evidence"),
            _component(None, "unresolved", "no performance evidence"),
        )
    summary = benchmark.get("summary", {}) if isinstance(benchmark.get("summary"), dict) else {}
    kind = str(benchmark.get("benchmark_kind") or summary.get("benchmark_kind") or "")
    quality = _number(summary.get("quality_score")) if kind in {"comparable_quality", "comparable_mixed"} else None
    performance = (
        _number(summary.get("performance_score")) if kind in {"comparable_performance", "comparable_mixed"} else None
    )
    return (
        _component(quality, "measured" if quality is not None else "unresolved", "typed comparable quality benchmark"),
        _component(
            performance,
            "measured" if performance is not None else "unresolved",
            "typed comparable performance benchmark",
        ),
    )


def _extension_component(
    model: dict[str, Any],
    extension: dict[str, Any],
) -> dict[str, Any] | None:
    values = model.get("score_contributions", {})
    raw = values.get(extension["source_key"]) if isinstance(values, dict) else None
    if isinstance(raw, dict):
        value = _number(raw.get("value"))
        source = str(raw.get("source") or "configured_extension")
        basis = str(raw.get("basis") or extension.get("description") or extension["name"])
    else:
        value = _number(raw)
        source = "configured_extension"
        basis = str(extension.get("description") or extension["name"])
    if value is not None and not 0 <= value <= 100:
        raise ValueError(f"scoring extension '{extension['name']}' value must be between 0 and 100")
    return _component(value, source, basis) if value is not None else None


def _validate_extensions(raw: object) -> list[dict[str, Any]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("placement_scoring.extensions must be a list")
    result = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name") or not item.get("source_key"):
            raise ValueError("each scoring extension needs name and source_key")
        weight = float(item.get("weight", 0))
        if weight <= 0 or weight > 1:
            raise ValueError("scoring extension weight must be greater than 0 and no more than 1")
        result.append(
            {
                "name": str(item["name"]),
                "source_key": str(item["source_key"]),
                "weight": weight,
                "description": item.get("description"),
            }
        )
    return result


def _capability_values(model: dict[str, Any]) -> list[float]:
    capabilities = model.get("capabilities", {})
    scores = capabilities.get("scores", {}) if isinstance(capabilities, dict) else {}
    values = [_number(value) for value in scores.values()] if isinstance(scores, dict) else []
    return [min(5.0, max(0.0, value)) for value in values if value is not None]


def _component(value: float | None, source: str, basis: str) -> dict[str, Any]:
    return {
        "value": round(min(100.0, max(0.0, value)), 2) if value is not None else None,
        "source": source,
        "basis": basis,
    }


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "", "null") else None
    except (TypeError, ValueError):
        return None
