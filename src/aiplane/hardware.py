from __future__ import annotations

import copy
import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .boundaries import CommandRunner, SubprocessCommandRunner
from .persistence import atomic_write_text
from .config import dump_yaml
from .evidence import evidence_provenance, evidence_source
from .hardware_discovery import discover_hardware, group_gpus
from .model_catalog import ModelCatalog, capability_profile
from .placement import assess_placement
from .runtime_catalog import RuntimeCatalog
from .scoring import score_model, scoring_profiles
from .policy import PolicyEngine
from .models import Profile
from .platform_support import HostPlatform, detect_host_platform


@dataclass(frozen=True)
class HardwareFit:
    model: str
    usable: bool
    reason: str


class HardwareManager:
    def __init__(
        self,
        profile: Profile,
        command_runner: CommandRunner | None = None,
        host_platform: HostPlatform | None = None,
    ):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
        self.host_platform = host_platform or detect_host_platform()
        self.config = profile.hardware or {}

    def show(self, verbosity: int = 0) -> dict[str, Any]:
        if verbosity != 0:
            result = copy.deepcopy(self.config)
            result["active_selection"] = self.active_config()
            result["effective_machine"] = self.machine()
            return result
        return {
            "active_selection": self.active_config(),
            "effective_machine": self.machine(),
        }

    def show_types(self) -> dict[str, Any]:
        types = []
        for name, template in self.templates().items():
            if not isinstance(template, dict):
                continue
            types.append(
                {
                    "name": name,
                    "provider": template.get("provider"),
                    "placement": template.get("placement"),
                    "substrate": template.get("substrate"),
                    "notes": template.get("notes"),
                }
            )
        return {
            "name": "hardware_types",
            "count": len(types),
            "types": sorted(types, key=lambda item: item["name"]),
        }

    def schema(self) -> dict[str, Any]:
        schema = self.config.get("machine_schema", {})
        return {
            "name": "machine_schema",
            "description": "Fields used to describe the effective machine for hardware-aware model recommendations.",
            "fields": schema if isinstance(schema, dict) else {},
            "example": {
                "machine_tag": "azure_nc40ads_h100_v5",
                "provider": "azure",
                "stock_sku": "Standard_NC40ads_H100_v5",
                "placement": "vm",
                "substrate": "docker",
                "cpu_cores": 40,
                "cpu_threads": 40,
                "memory_gb": 320,
                "gpu_vendor": "nvidia",
                "gpu_model": "H100 NVL",
                "gpu_count": 1,
                "vram_gb": 94,
                "total_vram_gb": 94,
                "accelerator_apis": ["cuda"],
                "os": "linux",
            },
        }

    def templates(self) -> dict[str, Any]:
        return self.config.get("hardware_profiles", {})

    def machine(self, discovered: dict[str, Any] | None = None) -> dict[str, Any]:
        discovered = discovered or self.discover()
        return _machine_from_active(self.active_config(), discovered)

    def active_config(self) -> dict[str, Any]:
        selected = self.config.get("selected")
        active = str(self.config.get("active", "local_auto"))
        if isinstance(selected, dict) and isinstance(selected.get("values"), dict):
            origin = selected.get("origin")
            values = copy.deepcopy(selected["values"])
            template = _template_values(self.templates().get(str(origin), {})) if origin else {}
            custom = bool(selected.get("custom", values != template))
            active_config = {
                "name": active,
                "origin": origin or "custom",
                "custom": custom or origin is None,
                "values": values,
            }
            active_config["machine"] = _machine_from_active(active_config, self.discover())
            return active_config

        template = self.templates().get(active)
        if isinstance(template, dict):
            active_config = {
                "name": active,
                "origin": active,
                "custom": False,
                "values": _template_values(template),
            }
            active_config["machine"] = _machine_from_active(active_config, self.discover())
            return active_config
        active_config = {
            "name": active,
            "origin": "custom",
            "custom": True,
            "values": {},
        }
        active_config["machine"] = _machine_from_active(active_config, self.discover())
        return active_config

    def use_template(self, template_name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        templates = self.templates()
        template = templates.get(template_name)
        if not isinstance(template, dict):
            raise ValueError(f"unknown hardware template: {template_name}")
        values = _template_values(template)
        overrides = overrides or {}
        values.update(overrides)
        self.config["active"] = template_name
        self.config["selected"] = {
            "origin": template_name,
            "custom": bool(overrides),
            "values": values,
        }
        self._write_config()
        return self.active_config()

    def customize_active(self, overrides: dict[str, Any]) -> dict[str, Any]:
        if not overrides:
            raise ValueError("at least one key=value override is required")
        active = self.active_config()
        values = copy.deepcopy(active.get("values", {}))
        values.update(overrides)
        origin = active.get("origin")
        self.config["selected"] = {
            "origin": None if origin == "custom" else origin,
            "custom": True,
            "values": values,
        }
        if self.config.get("active") is None:
            self.config["active"] = "custom"
        self._write_config()
        return self.active_config()

    def select_closest_discovered(self, dry_run: bool = False) -> dict[str, Any]:
        discovered = self.discover()
        closest = discovered.get("closest_profiles", [])
        selected = closest[0] if closest else None
        result: dict[str, Any] = {
            "discovered": discovered,
            "selected": None,
            "would_select": None,
            "dry_run": dry_run,
        }
        if not isinstance(selected, dict) or not selected.get("name"):
            result["note"] = "no close hardware template match was found"
            return result
        template_name = str(selected["name"])
        result["would_select" if dry_run else "selected"] = template_name
        if not dry_run:
            result["active"] = self.use_template(template_name)
        return result

    def clear_selection(self, dry_run: bool = False) -> dict[str, Any]:
        template = self.templates().get("local_auto")
        result = {
            "active": "local_auto",
            "dry_run": dry_run,
            "would_clear": dry_run,
            "cleared": not dry_run,
        }
        if dry_run:
            return result
        self.config["active"] = "local_auto"
        if isinstance(template, dict):
            self.config["selected"] = {
                "origin": "local_auto",
                "custom": False,
                "values": _template_values(template),
            }
        else:
            self.config.pop("selected", None)
        self._write_config()
        result["selection"] = self.active_config()
        return result

    def check_model_fit(self, model: dict[str, Any]) -> HardwareFit:
        discovered = self.discover()
        machine = self.machine(discovered)
        fit_basis = _discovered_from_machine(machine, discovered)
        return _fit_model(model, fit_basis)

    def _write_config(self) -> None:
        path = self.profile.root / "hardware.yaml"
        atomic_write_text(path, dump_yaml(self.config))

    def discover(self) -> dict[str, Any]:
        discovered = discover_hardware(self.command_runner, self.host_platform)
        discovered["closest_profiles"] = self._closest_profiles(discovered)
        return discovered

    def scoring(self) -> dict[str, Any]:
        return scoring_profiles(self.config)

    def assess(
        self,
        model_name: str,
        *,
        runtime: str | None = None,
        context_tokens: int | None = None,
        score_profile: str | None = None,
    ) -> dict[str, Any]:
        model = ModelCatalog(self.profile).show(model_name)
        discovered = self.discover()
        machine = self.machine(discovered)
        compatibility = _recommendation_runtime_compatibility(
            model_name, RuntimeCatalog(self.profile), model, runtime=runtime
        )
        selected_runtime = runtime or compatibility.get("recommended_runtime")
        placement = assess_placement(
            model,
            machine,
            runtime=str(selected_runtime or "") or None,
            context_tokens=context_tokens,
        )
        benchmark = _latest_benchmark_summaries(self.profile.workspace).get(model_name)
        score = score_model(
            model,
            placement,
            compatibility,
            config=self.config,
            profile_name=score_profile,
            benchmark=benchmark,
        )
        return {
            "model": model,
            "machine": machine,
            "runtime_compatibility": compatibility,
            "placement": placement,
            "score": score,
        }

    def doctor(self, model_name: str | None = None) -> dict[str, Any]:
        catalog = ModelCatalog(self.profile)
        discovered = self.discover()
        machine = self.machine(discovered)
        fit_basis = _discovered_from_machine(machine, discovered)
        if model_name:
            model_rows = [catalog.show(model_name)]
        else:
            model_rows = [{"name": name, **dict(model)} for name, model in catalog.models().items()]
        needs_fit: list[dict[str, Any]] = []
        no_fit_required: list[dict[str, Any]] = []
        for row in model_rows:
            fit = _fit_model(row, fit_basis)
            payload = fit.__dict__
            if bool(row.get("local", False)):
                needs_fit.append(payload)
            else:
                no_fit_required.append(payload)
        return {
            "machine": machine,
            "needs_fit_check": needs_fit,
            "no_local_fit_check_required": no_fit_required,
        }

    def recommend(
        self,
        include_not_recommended: bool = False,
        *,
        runtime: str | None = None,
        context_tokens: int | None = None,
        score_profile: str | None = None,
        roles: list[str] | None = None,
    ) -> dict[str, Any]:
        catalog = ModelCatalog(self.profile)
        runtime_catalog = RuntimeCatalog(self.profile)
        policy = PolicyEngine(self.profile)
        discovered = self.discover()
        machine = self.machine(discovered)
        fit_basis = _discovered_from_machine(machine, discovered)
        groups: dict[str, list[dict[str, Any]]] = {
            "recommended": [],
            "usable": [],
            "not_recommended": [],
            "remote_or_cloud": [],
        }
        benchmark_summaries = _latest_benchmark_summaries(self.profile.workspace)
        requested_roles = {str(role) for role in roles or []}

        for row in catalog.models().items():
            name, model = row
            model_roles = {str(role) for role in model.get("roles", []) if isinstance(role, str)}
            if requested_roles and not (model_roles & requested_roles):
                continue
            payload = dict(model)
            payload["name"] = name
            benchmark_summary = benchmark_summaries.get(name)
            policy_decision = policy.model_decision(name)
            if not bool(model.get("local", False)):
                groups["remote_or_cloud"].append(
                    _recommendation_payload(
                        payload,
                        "remote_or_cloud",
                        "remote/cloud model does not consume local inference hardware",
                        benchmark_summary,
                        policy_decision=policy_decision,
                        machine=machine,
                        discovered=discovered,
                    )
                )
                continue

            runtime_compatibility = _recommendation_runtime_compatibility(
                name, runtime_catalog, payload, runtime=runtime
            )
            selected_runtime = runtime or runtime_compatibility.get("recommended_runtime")
            placement = assess_placement(
                payload,
                machine,
                runtime=str(selected_runtime or "") or None,
                context_tokens=context_tokens,
            )
            level, reason = _recommend_model(
                payload,
                fit_basis,
                runtime_compatibility=runtime_compatibility,
                policy_decision=policy_decision,
            )
            if not placement["eligible"]:
                level = "not_recommended"
                reason = "; ".join(placement["blockers"][:3]) or "no feasible local placement mode"
            score = score_model(
                payload,
                placement,
                runtime_compatibility,
                config=self.config,
                profile_name=score_profile,
                benchmark=benchmark_summary,
            )
            recommendation = _recommendation_payload(
                payload,
                level,
                reason,
                benchmark_summary,
                runtime_compatibility=runtime_compatibility,
                policy_decision=policy_decision,
                machine=machine,
                discovered=discovered,
            )
            recommendation["placement"] = placement
            recommendation["score"] = score
            recommendation["selection_score"] = score["selection_score"]
            groups[level].append(recommendation)

        for rows in groups.values():
            rows.sort(
                key=lambda item: (
                    -item.get("selection_score", 0.0),
                    -item.get("capability_avg_score", 0.0),
                    -item.get("runtime_compatibility_score", 0.0),
                    item.get("provider", ""),
                    item.get("name", ""),
                )
            )
        ordered_groups: dict[str, list[dict[str, Any]]] = {
            "recommended": groups["recommended"],
            "usable": groups["usable"],
            "remote_or_cloud": groups["remote_or_cloud"],
        }
        if include_not_recommended:
            ordered_groups["not_recommended"] = groups["not_recommended"]

        criteria = {
            "recommended": "meets configured recommended RAM/VRAM targets, has policy approval, and is compatible with local runtime options",
            "usable": "meets configured minimum RAM/VRAM targets with policy and runtime caveats, but may be slow or tight",
            "remote_or_cloud": "fit is checked against provider quota/keys, not local RAM/VRAM",
        }
        if include_not_recommended:
            criteria["not_recommended"] = "does not meet local fit, local runtime compatibility, or policy constraints"
        return {
            "criteria": criteria,
            "machine": machine,
            "discovered": discovered,
            "provenance": _recommendation_run_provenance(machine, discovered, benchmark_summaries),
            "scoring": {
                "profile": score_profile or self.scoring()["default_profile"],
                "contract": "placement_readiness",
                "hard_eligibility_gate": True,
            },
            "models": ordered_groups,
            "hidden": (
                {
                    "not_recommended_count": len(groups["not_recommended"]),
                    "hint": "pass --include-not-recommended to show models that do not fit this hardware, runtime, or policy",
                    "nearest_miss": _nearest_miss(groups["not_recommended"]),
                }
                if not include_not_recommended
                else {}
            ),
        }

    def _closest_profiles(self, discovered: dict[str, Any]) -> list[dict[str, Any]]:
        profiles = self.config.get("hardware_profiles", {})
        if not isinstance(profiles, dict):
            return []
        scored = []
        for name, template in profiles.items():
            if not isinstance(template, dict) or name == "local_auto":
                continue
            score, reasons = _score_template(template, discovered)
            if score <= 0:
                continue
            scored.append(
                {
                    "name": name,
                    "score": score,
                    "reasons": reasons,
                    "notes": template.get("notes"),
                }
            )
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:3]


def _nearest_miss(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    row = rows[0]
    name = str(row.get("name") or "")
    return {
        "name": name,
        "reason": row.get("reason") or "does not meet the active local constraints",
        "remediation": "aiplane recommend --include-not-recommended",
    }


def _machine_from_active(active: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    values = active.get("values", {}) if isinstance(active, dict) else {}
    if not isinstance(values, dict):
        values = {}
    gpus = [gpu for gpu in discovered.get("gpus", []) if isinstance(gpu, dict)]
    first_gpu = gpus[0] if gpus else {}
    max_vram = _max_vram_gb(discovered)
    total_discovered_vram = _sum_vram_gb(discovered)
    max_free_vram = _max_free_vram_gb(discovered)
    total_free_vram = _sum_free_vram_gb(discovered)
    cpu_threads = _resolve_number(values.get("cpu_threads"), discovered.get("cpu_count"))
    cpu_cores = _resolve_number(values.get("cpu_cores", values.get("cpu")), cpu_threads)
    ram = _resolve_number(values.get("memory_gb"), discovered.get("memory_gb"))
    unified = _resolve_number(values.get("unified_memory_gb"), None)
    vram = _resolve_number(values.get("vram_gb"), max_vram)
    total_vram = _resolve_number(values.get("total_vram_gb"), total_discovered_vram)
    gpu_count = _resolve_number(values.get("gpu_count"), len(gpus))
    gpu_vendor = _resolve_text(
        values.get("gpu_vendor", values.get("vendor")),
        first_gpu.get("vendor") if first_gpu else None,
    )
    gpu_model = _resolve_text(values.get("gpu_model"), first_gpu.get("name") if first_gpu else None)
    return {
        "name": active.get("name") or values.get("machine_tag") or "custom",
        "origin": active.get("origin") or "custom",
        "custom": bool(active.get("custom", True)),
        "stock": {
            "machine_tag": values.get("machine_tag") or active.get("name") or "custom",
            "provider": values.get("provider"),
            "stock_sku": values.get("stock_sku") or values.get("instance_type") or values.get("gpu_sku"),
        },
        "placement": values.get("placement") or values.get("type"),
        "substrate": values.get("substrate"),
        "cpu": {
            "architecture": _resolve_text(values.get("cpu_architecture"), discovered.get("machine")),
            "cores": cpu_cores,
            "threads": cpu_threads,
        },
        "memory": {
            "ram_gb": ram,
            "unified_memory_gb": unified,
            "memory_architecture": values.get("memory_architecture"),
            "memory_bandwidth_gbps": _resolve_number(values.get("memory_bandwidth_gbps"), None),
        },
        "gpu": {
            "vendor": gpu_vendor or "none",
            "model": gpu_model or "none",
            "count": gpu_count,
            "vram_gb": vram,
            "free_vram_gb": max_free_vram,
            "total_vram_gb": total_vram,
            "total_free_vram_gb": total_free_vram,
            "indices": values.get("gpu_indices"),
            "devices": copy.deepcopy(gpus),
            "groups": copy.deepcopy(discovered.get("gpu_groups") or group_gpus(gpus)),
            "topology": copy.deepcopy(discovered.get("topology", {"state": "not_available", "links": []})),
        },
        "accelerator_apis": values.get("accelerator_apis") or _default_accelerators(str(gpu_vendor or "")),
        "os": _resolve_text(values.get("os"), platform.system().lower()),
        "notes": values.get("notes"),
    }


def _discovered_from_machine(machine: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(discovered)
    memory = machine.get("memory", {}) if isinstance(machine.get("memory"), dict) else {}
    gpu = machine.get("gpu", {}) if isinstance(machine.get("gpu"), dict) else {}
    ram = _float_or_none(memory.get("ram_gb")) or _float_or_none(memory.get("unified_memory_gb"))
    if ram is not None:
        result["memory_gb"] = ram
    vram = _float_or_none(gpu.get("vram_gb")) or _float_or_none(memory.get("unified_memory_gb")) or 0.0
    count = int(_float_or_none(gpu.get("count")) or (1 if vram else 0))
    vendor = str(gpu.get("vendor") or "unknown")
    model = str(gpu.get("model") or "configured GPU")
    if count <= 0 or vendor == "none":
        result["gpus"] = []
    elif vram:
        result["gpus"] = [
            {
                "vendor": vendor,
                "name": model,
                "vram_mb": int(vram * 1024),
                "configured": True,
            }
            for _ in range(count)
        ]
    return result


def _resolve_number(value: object, fallback: object = None) -> float | int | None:
    if value in (None, "", "null", "provider_defined", "node_pool_defined"):
        return _numeric_fallback(fallback)
    if str(value).lower() == "auto":
        return _numeric_fallback(fallback)
    parsed_range = _parse_range(value)
    if parsed_range:
        return parsed_range[0]
    return _numeric_fallback(value)


def _numeric_fallback(value: object) -> float | int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


def _resolve_text(value: object, fallback: object = None) -> str | None:
    if value in (None, "", "auto", "provider_defined", "node_pool_defined"):
        return str(fallback) if fallback not in (None, "") else None
    return str(value)


def _default_accelerators(vendor: str) -> list[str]:
    vendor = vendor.lower()
    if "nvidia" in vendor:
        return ["cuda"]
    if "amd" in vendor:
        return ["rocm", "vulkan"]
    if "apple" in vendor:
        return ["metal"]
    return ["cpu"]


def _average_capability_score(item: dict[str, Any]) -> float:
    capabilities = item.get("capabilities")
    if not isinstance(capabilities, dict):
        return 0.0
    scores = capabilities.get("scores")
    if not isinstance(scores, dict) or not scores:
        return 0.0
    values = []
    for value in scores.values():
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _template_values(template: object) -> dict[str, Any]:
    if not isinstance(template, dict):
        return {}
    values = copy.deepcopy(template)
    values.pop("configurable_options", None)
    return values


def _score_template(template: dict[str, Any], discovered: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    gpus = discovered.get("gpus", [])
    vendors = {str(gpu.get("vendor", "")).lower() for gpu in gpus if isinstance(gpu, dict)}
    memory_gb = discovered.get("memory_gb")
    max_vram_gb = _max_vram_gb(discovered)

    vendor = str(template.get("gpu_vendor") or template.get("vendor") or "").lower()
    gpu_count = _resolve_number(template.get("gpu_count"), None)
    placement = str(template.get("placement") or template.get("type") or "").lower()

    if vendor in {"none", "cpu"} and not gpus:
        score += 40
        reasons.append("no local GPU discovered")
    if vendor and vendor in vendors:
        score += 50
        reasons.append(f"{vendor} GPU discovered")
    if not gpus and placement in {"same_host", "workstation"} and gpu_count in (None, 0):
        score += 20
        reasons.append("local CPU/system-memory profile")
    if max_vram_gb:
        vram_range = _parse_range(template.get("vram_gb"))
        if vram_range and vram_range[0] <= max_vram_gb <= vram_range[1]:
            score += 25
            reasons.append(f"GPU VRAM {max_vram_gb:.1f}GB fits template range")
        elif vram_range and max_vram_gb >= vram_range[0]:
            score += 15
            reasons.append(f"GPU VRAM {max_vram_gb:.1f}GB meets template minimum")
    if memory_gb:
        mem_range = _parse_range(template.get("memory_gb") or template.get("unified_memory_gb"))
        if mem_range and mem_range[0] <= float(memory_gb) <= mem_range[1]:
            score += 15
            reasons.append(f"system memory {memory_gb:g}GB fits template range")
        elif mem_range and float(memory_gb) >= mem_range[0]:
            score += 10
            reasons.append(f"system memory {memory_gb:g}GB meets template minimum")
    if not reasons:
        reasons.append("template is available but no strong local match was detected")
    return score, reasons


def _parse_range(value: object) -> tuple[float, float] | None:
    if value in (None, "", "null", "auto", "provider_defined", "node_pool_defined"):
        return None
    text = str(value)
    if "-" in text:
        left, right = text.split("-", 1)
        try:
            return float(left), float(right)
        except ValueError:
            return None
    try:
        number = float(text)
        return number, number
    except ValueError:
        return None


def _recommendation_payload(
    model: dict[str, Any],
    level: str,
    reason: str,
    benchmark_summary: dict[str, Any] | None = None,
    runtime_compatibility: dict[str, Any] | None = None,
    policy_decision: Any | None = None,
    *,
    machine: dict[str, Any] | None = None,
    discovered: dict[str, Any] | None = None,
) -> dict[str, Any]:
    capabilities = capability_profile(model)
    payload = {
        "name": model.get("name"),
        "model": model.get("model"),
        "provider": model.get("provider"),
        "capability_avg_score": _average_capability_score({"capabilities": capabilities}),
        "level": level,
        "enabled": bool(model.get("enabled", True)),
        "min_ram_gb": model.get("min_ram_gb"),
        "recommended_ram_gb": model.get("recommended_ram_gb"),
        "min_vram_gb": model.get("min_vram_gb"),
        "recommended_vram_gb": model.get("recommended_vram_gb"),
        "reason": reason,
        "roles": sorted(str(role) for role in model.get("roles", []) if isinstance(role, str)),
    }
    if runtime_compatibility:
        payload["runtime_compatibility"] = {
            "state": runtime_compatibility.get("state"),
            "supported_runtimes": runtime_compatibility.get("supported_runtimes", []),
            "available_runtimes": runtime_compatibility.get("available_runtimes", []),
            "preferred_runtime": runtime_compatibility.get("preferred_runtime"),
            "recommended_runtime": runtime_compatibility.get("recommended_runtime"),
            "reasoning": runtime_compatibility.get("reasoning", []),
        }
        payload["runtime_compatibility_score"] = float(runtime_compatibility.get("compatibility_score", 0.0) or 0.0)
        payload["runtime_recommendation"] = runtime_compatibility.get("recommended_runtime")
    else:
        payload["runtime_compatibility_score"] = 0.0
        payload["runtime_recommendation"] = None
        payload["runtime_compatibility"] = {
            "state": "not_applicable",
            "supported_runtimes": [],
            "available_runtimes": [],
            "preferred_runtime": None,
            "recommended_runtime": None,
            "reasoning": ["remote or non-local model"],
        }
    if policy_decision is not None:
        payload["policy_decision"] = {
            "outcome": str(getattr(policy_decision, "outcome", "allowed")),
            "allowed": bool(policy_decision.allowed),
            "requires_approval": bool(policy_decision.requires_approval),
            "reason": policy_decision.reason,
            "matched_rule": policy_decision.matched_rule,
        }
    payload["pull_command"] = model.get("pull_command")
    payload["notes"] = model.get("notes")
    payload["capabilities"] = capabilities
    if benchmark_summary:
        payload["latest_benchmark"] = benchmark_summary
    payload["provenance"] = _model_recommendation_provenance(
        model,
        machine or {},
        discovered or {},
        runtime_compatibility,
        policy_decision,
        benchmark_summary,
    )
    return payload


def _recommendation_run_provenance(
    machine: dict[str, Any],
    discovered: dict[str, Any],
    benchmark_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    detected = {
        "cpu_count": discovered.get("cpu_count"),
        "memory_gb": discovered.get("memory_gb"),
        "gpu_count": len(discovered.get("gpus", []) or []),
    }
    unresolved = sorted(key for key, value in detected.items() if value is None)
    sources = [
        evidence_source("model_catalog", "configured", "models.yaml"),
        evidence_source("active_machine", "configured", "hardware.yaml#/selected", value=machine.get("name")),
        evidence_source("current_machine", "detected", "hardware.discover", value=detected),
        evidence_source("runtime_compatibility", "generated", "runtime_catalog"),
        evidence_source("policy", "configured", "repository.yaml + approvals.yaml"),
    ]
    return evidence_provenance(
        sources,
        uncertainty=[f"live hardware fact is unavailable: {name}" for name in unresolved],
        method="deterministic_fit_runtime_policy_capability_order",
        machine={"name": machine.get("name"), "origin": machine.get("origin")},
        benchmark_records=len(benchmark_summaries),
        benchmark_role="context_only_not_used_for_ranking",
        unresolved_detected_facts=unresolved,
    )


def _model_recommendation_provenance(
    model: dict[str, Any],
    machine: dict[str, Any],
    discovered: dict[str, Any],
    runtime_compatibility: dict[str, Any] | None,
    policy_decision: Any | None,
    benchmark_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    name = str(model.get("name") or "")
    runtime_state = str((runtime_compatibility or {}).get("state") or "not_applicable")
    policy_state = str(getattr(policy_decision, "outcome", "not_evaluated"))
    sources: list[dict[str, Any]] = [
        {
            "state": "configured",
            "source": f"models.yaml#/models/{name}",
            "name": "model",
        },
        {
            "state": "configured",
            "source": "hardware.yaml#/selected",
            "name": "machine",
            "value": machine.get("name"),
        },
        {
            "state": "detected",
            "source": "hardware.discover",
            "name": "hardware",
            "value": {
                "cpu_count": discovered.get("cpu_count"),
                "memory_gb": discovered.get("memory_gb"),
                "gpu_count": len(discovered.get("gpus", []) or []),
            },
        },
        {
            "state": "generated",
            "source": "runtime_catalog",
            "name": "runtime_compatibility",
            "value": runtime_state,
        },
        {
            "state": "configured",
            "source": "repository.yaml + approvals.yaml",
            "name": "policy",
            "value": policy_state,
        },
    ]
    uncertainty: list[str] = [
        "capability scores are catalog metadata and are not measured task-quality evidence",
        "benchmark records are shown as context and do not affect this deterministic ranking",
    ]
    summary = benchmark_summary.get("summary", {}) if isinstance(benchmark_summary, dict) else {}
    sample_count = sum(
        int(summary.get(key, 0) or 0)
        for key in ("passed", "failed", "previewed")
        if isinstance(summary.get(key, 0), (int, float))
    )
    if benchmark_summary:
        sources.append(
            {
                "state": "measured",
                "source": benchmark_summary.get("path"),
                "name": "latest_benchmark",
                "sample_count": sample_count,
            }
        )
        if sample_count == 0:
            uncertainty.append("latest benchmark summary does not report a task sample count")
    else:
        sources.append(
            {
                "state": "unresolved",
                "source": None,
                "name": "latest_benchmark",
                "sample_count": 0,
            }
        )
        uncertainty.append("no local benchmark record is available for this model")
    if runtime_state == "runtime_supported_only":
        uncertainty.append("a compatible runtime is configured but was not detected as available")
    if runtime_state == "no_supported_runtime":
        uncertainty.append("no supported local runtime is known")
    if discovered.get("memory_gb") is None:
        uncertainty.append("live system memory discovery is unavailable; configured machine values may be used")
    return evidence_provenance(
        sources,
        sample_count=sample_count,
        uncertainty=uncertainty,
        method="deterministic_model_fit_explanation",
    )


def _recommendation_runtime_compatibility(
    model_name: str,
    runtime_catalog: RuntimeCatalog,
    model: dict[str, Any],
    *,
    runtime: str | None = None,
) -> dict[str, Any]:
    if not bool(model.get("local", False)):
        return {
            "state": "not_local_model",
            "supported_runtimes": [],
            "available_runtimes": [],
            "preferred_runtime": None,
            "recommended_runtime": None,
            "compatibility_score": 0.0,
            "reasoning": ["model does not use a local runtime"],
        }

    supported_runtimes = runtime_catalog.compatible_runtimes_for_entry(model, include_gui=False)
    if runtime and runtime not in supported_runtimes:
        return {
            "state": "no_supported_runtime",
            "supported_runtimes": sorted(set(supported_runtimes)),
            "available_runtimes": [],
            "preferred_runtime": str(model.get("preferred_runtime") or "") or None,
            "recommended_runtime": None,
            "compatibility_score": 0.0,
            "reasoning": [f"model does not declare support for requested runtime '{runtime}'"],
        }
    if runtime:
        supported_runtimes = [runtime]
    if not supported_runtimes:
        return {
            "state": "no_supported_runtime",
            "supported_runtimes": [],
            "available_runtimes": [],
            "preferred_runtime": str(model.get("preferred_runtime") or "") or None,
            "recommended_runtime": None,
            "compatibility_score": 0.0,
            "reasoning": ["no local runtime is known for this model"],
        }

    statuses = [runtime_catalog.runtime_available(runtime) for runtime in supported_runtimes]
    available = [str(row.get("name")) for row in statuses if bool(row.get("available"))]
    preferred = runtime or str(model.get("preferred_runtime") or "").strip()
    preferred_runtime = supported_runtimes[0] if not preferred else preferred

    if preferred and preferred in available:
        return {
            "state": "preferred_runtime_available",
            "supported_runtimes": sorted(set(supported_runtimes)),
            "available_runtimes": sorted(set(available)),
            "preferred_runtime": preferred,
            "recommended_runtime": preferred,
            "compatibility_score": 1.0,
            "reasoning": [f"preferred runtime '{preferred}' is available"],
        }

    if available:
        return {
            "state": "runtime_available",
            "supported_runtimes": sorted(set(supported_runtimes)),
            "available_runtimes": sorted(set(available)),
            "preferred_runtime": preferred or None,
            "recommended_runtime": available[0],
            "compatibility_score": 0.8,
            "reasoning": ["model has supported runtimes with local availability"],
        }

    return {
        "state": "runtime_supported_only",
        "supported_runtimes": sorted(set(supported_runtimes)),
        "available_runtimes": [],
        "preferred_runtime": preferred or None,
        "recommended_runtime": preferred_runtime,
        "compatibility_score": 0.4,
        "reasoning": ["model has local runtime compatibility, but none are currently available"],
    }


def _latest_benchmark_summaries(workspace: Path) -> dict[str, dict[str, Any]]:
    root = workspace / ".aiplane" / "benchmarks"
    if not root.is_dir():
        return {}
    summaries: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        model_name = str(payload.get("model_name") or "")
        if not model_name:
            continue
        summaries[model_name] = {
            "created_at": payload.get("created_at"),
            "summary": payload.get("summary", {}),
            "path": str(path),
        }
    return summaries


def _recommend_model(
    model: dict[str, Any],
    discovered: dict[str, Any],
    runtime_compatibility: dict[str, Any] | None = None,
    policy_decision: Any | None = None,
) -> tuple[str, str]:
    if policy_decision is not None and not bool(policy_decision.allowed):
        return "not_recommended", policy_decision.reason

    compatibility_state = str((runtime_compatibility or {}).get("state"))
    if compatibility_state == "no_supported_runtime":
        return "not_recommended", "; ".join(
            (runtime_compatibility or {}).get("reasoning", ["no local runtime support"])
        )

    runtime_warning = ""
    if compatibility_state == "runtime_supported_only":
        runtime_warning = "; ".join((runtime_compatibility or {}).get("reasoning", []))

    memory_gb = _float_or_none(discovered.get("memory_gb"))
    gpu_vram_gb = _max_vram_gb(discovered)
    min_ram = _float_or_none(model.get("min_ram_gb"))
    recommended_ram = _float_or_none(model.get("recommended_ram_gb"))
    min_vram = _float_or_none(model.get("min_vram_gb"))
    recommended_vram = _float_or_none(model.get("recommended_vram_gb"))

    blockers: list[str] = []
    if min_ram is not None and memory_gb is not None and memory_gb < min_ram:
        blockers.append(f"needs at least {min_ram:g}GB RAM; discovered {memory_gb:g}GB")
    if min_vram is not None and gpu_vram_gb < min_vram:
        blockers.append(f"needs at least {min_vram:g}GB VRAM; discovered {gpu_vram_gb:.1f}GB")
    if blockers:
        if runtime_warning:
            blockers.append(runtime_warning)
        return "not_recommended", "; ".join(blockers)
    gaps: list[str] = []
    if recommended_ram is not None and memory_gb is not None and memory_gb < recommended_ram:
        gaps.append(f"below recommended RAM ({memory_gb:g}GB < {recommended_ram:g}GB)")
    if recommended_vram is not None and gpu_vram_gb < recommended_vram:
        gaps.append(f"below recommended VRAM ({gpu_vram_gb:.1f}GB < {recommended_vram:g}GB)")
    if runtime_warning and not gaps:
        return (
            "recommended",
            f"{runtime_warning}; meets policy, runtime compatibility, and configured RAM/VRAM targets",
        )
    if gaps:
        if runtime_warning:
            gaps.append(runtime_warning)
        return "usable", "; ".join(gaps)
    return "recommended", "meets policy, runtime compatibility, and configured RAM/VRAM targets"


def _gpu_memory_value(gpu: dict[str, Any], key_gb: str, key_mb: str) -> float | None:
    value = _float_or_none(gpu.get(key_gb))
    if value is not None:
        return value
    mib = _float_or_none(gpu.get(key_mb))
    return mib / 1024 if mib is not None else None


def _max_vram_gb(discovered: dict[str, Any]) -> float:
    values = [
        value
        for gpu in discovered.get("gpus", [])
        if isinstance(gpu, dict)
        for value in [_gpu_memory_value(gpu, "vram_gb", "vram_mb")]
        if value is not None
    ]
    return max(values, default=0.0)


def _sum_vram_gb(discovered: dict[str, Any]) -> float:
    values = [
        value
        for gpu in discovered.get("gpus", [])
        if isinstance(gpu, dict)
        for value in [_gpu_memory_value(gpu, "vram_gb", "vram_mb")]
        if value is not None
    ]
    return round(sum(values), 2)


def _max_free_vram_gb(discovered: dict[str, Any]) -> float | None:
    values = [
        value
        for gpu in discovered.get("gpus", [])
        if isinstance(gpu, dict)
        for value in [_gpu_memory_value(gpu, "free_vram_gb", "free_vram_mb")]
        if value is not None
    ]
    return max(values, default=None)


def _sum_free_vram_gb(discovered: dict[str, Any]) -> float | None:
    gpus = [gpu for gpu in discovered.get("gpus", []) if isinstance(gpu, dict)]
    values = [_gpu_memory_value(gpu, "free_vram_gb", "free_vram_mb") for gpu in gpus]
    return (
        round(sum(value for value in values if value is not None), 2)
        if gpus and all(value is not None for value in values)
        else None
    )


def _fit_model(model: dict[str, Any], discovered: dict[str, Any]) -> HardwareFit:
    model_id = str(model.get("model", model.get("name", "unknown")))
    if not bool(model.get("local", False)):
        return HardwareFit(model_id, True, "remote/cloud model does not require local fit check")

    memory_gb = discovered.get("memory_gb")
    min_ram = _float_or_none(model.get("min_ram_gb"))
    recommended_ram = _float_or_none(model.get("recommended_ram_gb"))
    min_vram = _float_or_none(model.get("min_vram_gb"))
    gpu_vram_gb = _max_vram_gb(discovered)

    if min_ram is not None and memory_gb is not None and memory_gb < min_ram:
        return HardwareFit(
            model_id,
            False,
            f"requires at least {min_ram:g}GB RAM; discovered {memory_gb:g}GB",
        )
    if min_vram is not None and gpu_vram_gb < min_vram:
        return HardwareFit(
            model_id,
            False,
            f"requires at least {min_vram:g}GB VRAM; discovered {gpu_vram_gb:.1f}GB",
        )
    if recommended_ram is not None and memory_gb is not None and memory_gb < recommended_ram:
        return HardwareFit(
            model_id,
            True,
            f"usable but below recommended RAM ({memory_gb:g}GB < {recommended_ram:g}GB)",
        )
    return HardwareFit(model_id, True, "hardware appears sufficient for configured minimums")


def _float_or_none(value: object) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
