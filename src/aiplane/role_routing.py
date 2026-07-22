"""Evidence-backed model comparisons for a configured stack role."""

from __future__ import annotations

from typing import Any

from .hardware import HardwareManager
from .models import Profile

ROLE_CAPABILITIES = {
    "chat": "general_chat",
    "analysis": "code_analysis",
    "code": "code_generation",
    "generation": "code_generation",
    "completion": "code_completion",
    "autocomplete": "code_completion",
    "reasoning": "reasoning",
    "embedding": "embedding",
    "tool_use": "tool_use",
}


def compare_role_models(
    profile: Profile,
    role: str,
    *,
    candidates: list[str] | None = None,
    runtime: str | None = None,
    context_tokens: int | None = None,
    score_profile: str | None = None,
) -> dict[str, Any]:
    role_name = role.strip()
    if not role_name:
        raise ValueError("role is required")
    assessment = HardwareManager(profile).recommend(
        include_not_recommended=True,
        runtime=runtime,
        context_tokens=context_tokens,
        score_profile=score_profile,
    )
    selected = set(candidates or [])
    known: set[str] = set()
    rows: list[dict[str, Any]] = []
    capability_key = ROLE_CAPABILITIES.get(role_name, role_name)
    for group in assessment["models"].values():
        for model in group:
            name = str(model.get("name") or "")
            known.add(name)
            configured = profile.models.get("models", {}).get(name, {})
            roles = {str(value) for value in configured.get("roles", [])} if isinstance(configured, dict) else set()
            if selected and name not in selected:
                continue
            if not selected and role_name not in roles and capability_key not in roles:
                continue
            policy = model.get("policy_decision", {})
            latest_benchmark = model.get("latest_benchmark", {})
            summary = (
                latest_benchmark.get("summary", {})
                if isinstance(latest_benchmark.get("summary"), dict)
                else latest_benchmark
            )
            benchmark_kind = str(summary.get("benchmark_kind") or "")
            measured_quality = (
                summary.get("quality_score") if benchmark_kind in {"comparable_quality", "comparable_mixed"} else None
            )
            capabilities = model.get("capabilities", {}).get("scores", {})
            role_score = capabilities.get(capability_key) if isinstance(capabilities, dict) else None
            eligible = bool(policy.get("allowed", True)) and model.get("level") != "not_recommended"
            rows.append(
                {
                    "name": name,
                    "model": model.get("model"),
                    "provider": model.get("provider"),
                    "eligible": eligible,
                    "policy": policy,
                    "placement": {
                        "level": model.get("level"),
                        "selection_score": model.get("selection_score"),
                        "reason": model.get("reason"),
                    },
                    "task_suitability": {
                        "capability": capability_key,
                        "configured_score": role_score,
                        "source": "catalog_metadata" if role_score is not None else "unresolved",
                    },
                    "measured_quality": {
                        "value": measured_quality,
                        "benchmark_kind": benchmark_kind or None,
                        "sample_count": summary.get("sample_count"),
                        "path": latest_benchmark.get("path"),
                    },
                    "score_components": model.get("score", {}).get("components", {}),
                    "runtime": model.get("runtime_recommendation"),
                    "provenance": model.get("provenance"),
                }
            )
    missing = sorted(selected - known)
    if missing:
        raise ValueError(f"unknown model aliases: {', '.join(missing)}")
    if not rows:
        raise ValueError(f"no configured model candidates found for role {role_name!r}")
    rows.sort(key=_routing_key)
    return {
        "contract_version": "1.0",
        "record_type": "role_model_comparison",
        "role": role_name,
        "selection_method": [
            "hard policy and placement eligibility",
            "comparable measured task quality when present",
            "configured role suitability",
            "placement-readiness score",
        ],
        "recommended": rows[0] if rows[0]["eligible"] else None,
        "alternatives": rows,
        "machine": assessment["machine"],
        "scoring": assessment["scoring"],
        "notes": [
            "Task quality, placement readiness, performance, and policy are not collapsed into one universal score.",
            "User score contributions appear under score_components when configured in hardware.yaml and models.yaml.",
        ],
    }


def _routing_key(row: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
    measured = row["measured_quality"].get("value")
    suitability = row["task_suitability"].get("configured_score")
    placement = row["placement"].get("selection_score")
    return (
        -float(bool(row["eligible"])),
        -float(measured is not None),
        -float(measured or 0),
        -float(suitability or 0),
        -float(placement or 0),
        str(row["name"]),
    )
