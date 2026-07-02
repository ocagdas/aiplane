from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import dump_yaml
from .model_catalog import ModelCatalog, capability_profile
from .models import Profile


@dataclass(frozen=True)
class HardwareFit:
    model: str
    usable: bool
    reason: str


class HardwareManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.hardware or {}

    def show(self) -> dict[str, Any]:
        result = copy.deepcopy(self.config)
        result["active_selection"] = self.active_config()
        result["effective_machine"] = self.machine()
        return result

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
        path.write_text(dump_yaml(self.config), encoding="utf-8")

    def discover(self) -> dict[str, Any]:
        discovered: dict[str, Any] = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "memory_gb": _memory_gb(),
            "gpus": [],
            "notes": [],
        }
        discovered["gpus"].extend(_nvidia_gpus())
        discovered["gpus"].extend(_amd_gpus())
        if not discovered["gpus"]:
            discovered["notes"].append("No NVIDIA/AMD GPU discovered through available CLI tools")
        discovered["closest_profiles"] = self._closest_profiles(discovered)
        return discovered

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

    def recommend(self, include_not_recommended: bool = False) -> dict[str, Any]:
        catalog = ModelCatalog(self.profile)
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
        for row in catalog.models().items():
            name, model = row
            payload = dict(model)
            payload["name"] = name
            benchmark_summary = benchmark_summaries.get(name)
            if not bool(model.get("local", False)):
                groups["remote_or_cloud"].append(
                    _recommendation_payload(
                        payload,
                        "remote_or_cloud",
                        "remote/cloud model does not consume local inference hardware",
                        benchmark_summary,
                    )
                )
                continue
            level, reason = _recommend_model(payload, fit_basis)
            groups[level].append(_recommendation_payload(payload, level, reason, benchmark_summary))
        ordered_groups: dict[str, list[dict[str, Any]]] = {
            "recommended": groups["recommended"],
            "usable": groups["usable"],
            "remote_or_cloud": groups["remote_or_cloud"],
        }
        if include_not_recommended:
            ordered_groups["not_recommended"] = groups["not_recommended"]
        for rows in ordered_groups.values():
            rows.sort(
                key=lambda item: (
                    -_average_capability_score(item),
                    item.get("provider", ""),
                    item.get("name", ""),
                )
            )
        criteria = {
            "recommended": "meets configured recommended RAM and VRAM targets for reasonable local use",
            "usable": "meets configured minimum RAM and VRAM targets, but may be slow or tight",
            "remote_or_cloud": "fit is checked against provider quota/keys, not local RAM/VRAM",
        }
        if include_not_recommended:
            criteria["not_recommended"] = "does not meet configured minimum local load/run targets"
        return {
            "criteria": criteria,
            "machine": machine,
            "discovered": discovered,
            "models": ordered_groups,
            "hidden": {
                "not_recommended_count": len(groups["not_recommended"]),
                "hint": "pass --include-not-recommended to show models that do not fit this hardware",
            }
            if not include_not_recommended
            else {},
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


def _machine_from_active(active: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    values = active.get("values", {}) if isinstance(active, dict) else {}
    if not isinstance(values, dict):
        values = {}
    gpus = [gpu for gpu in discovered.get("gpus", []) if isinstance(gpu, dict)]
    first_gpu = gpus[0] if gpus else {}
    max_vram = _max_vram_gb(discovered)
    cpu_threads = _resolve_number(values.get("cpu_threads"), discovered.get("cpu_count"))
    cpu_cores = _resolve_number(values.get("cpu_cores", values.get("cpu")), cpu_threads)
    ram = _resolve_number(values.get("memory_gb"), discovered.get("memory_gb"))
    unified = _resolve_number(values.get("unified_memory_gb"), None)
    vram = _resolve_number(values.get("vram_gb"), max_vram)
    total_vram = _resolve_number(values.get("total_vram_gb"), max_vram)
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
            "total_vram_gb": total_vram,
            "indices": values.get("gpu_indices"),
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


def _memory_gb() -> float | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                return round(kb / 1024 / 1024, 2)
    return None


def _nvidia_gpus() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,uuid",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return []
    gpus = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            gpus.append(
                {
                    "vendor": "nvidia",
                    "name": parts[0],
                    "vram_mb": int(parts[1]),
                    "uuid": parts[2],
                }
            )
    return gpus


def _amd_gpus() -> list[dict[str, Any]]:
    # Prefer rocminfo/rocm-smi when available; fall back to lspci names only.
    gpus: list[dict[str, Any]] = []
    if shutil.which("rocm-smi"):
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpus.append(
                {
                    "vendor": "amd",
                    "name": "AMD GPU detected by rocm-smi",
                    "details": result.stdout.strip()[-1000:],
                }
            )
            return gpus
    if shutil.which("lspci"):
        result = subprocess.run(["lspci"], text=True, capture_output=True, check=False)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                lower = line.lower()
                if "amd" in lower and ("vga" in lower or "display" in lower or "3d" in lower):
                    gpus.append({"vendor": "amd", "name": line.strip()})
    return gpus


def _score_template(template: dict[str, Any], discovered: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    gpus = discovered.get("gpus", [])
    vendors = {str(gpu.get("vendor", "")).lower() for gpu in gpus if isinstance(gpu, dict)}
    memory_gb = discovered.get("memory_gb")
    max_vram_gb = 0.0
    for gpu in gpus:
        if isinstance(gpu, dict) and "vram_mb" in gpu:
            max_vram_gb = max(max_vram_gb, float(gpu["vram_mb"]) / 1024)

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
        "pull_command": model.get("pull_command"),
        "notes": model.get("notes"),
        "capabilities": capabilities,
    }
    if benchmark_summary:
        payload["latest_benchmark"] = benchmark_summary
    return payload


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


def _recommend_model(model: dict[str, Any], discovered: dict[str, Any]) -> tuple[str, str]:
    memory_gb = _float_or_none(discovered.get("memory_gb"))
    gpu_vram_gb = _max_vram_gb(discovered)
    min_ram = _float_or_none(model.get("min_ram_gb"))
    recommended_ram = _float_or_none(model.get("recommended_ram_gb"))
    min_vram = _float_or_none(model.get("min_vram_gb"))
    recommended_vram = _float_or_none(model.get("recommended_vram_gb"))

    blockers = []
    if min_ram is not None and memory_gb is not None and memory_gb < min_ram:
        blockers.append(f"needs at least {min_ram:g}GB RAM; discovered {memory_gb:g}GB")
    if min_vram is not None and gpu_vram_gb < min_vram:
        blockers.append(f"needs at least {min_vram:g}GB VRAM; discovered {gpu_vram_gb:.1f}GB")
    if blockers:
        return "not_recommended", "; ".join(blockers)

    gaps = []
    if recommended_ram is not None and memory_gb is not None and memory_gb < recommended_ram:
        gaps.append(f"below recommended RAM ({memory_gb:g}GB < {recommended_ram:g}GB)")
    if recommended_vram is not None and gpu_vram_gb < recommended_vram:
        gaps.append(f"below recommended VRAM ({gpu_vram_gb:.1f}GB < {recommended_vram:g}GB)")
    if gaps:
        return "usable", "; ".join(gaps)
    return "recommended", "meets configured recommended RAM/VRAM targets"


def _max_vram_gb(discovered: dict[str, Any]) -> float:
    gpu_vram_gb = 0.0
    for gpu in discovered.get("gpus", []):
        if isinstance(gpu, dict) and "vram_mb" in gpu:
            gpu_vram_gb = max(gpu_vram_gb, float(gpu["vram_mb"]) / 1024)
    return gpu_vram_gb


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
