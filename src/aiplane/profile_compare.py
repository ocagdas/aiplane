from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from .boundaries import CommandRunner
from .config import parse_yaml
from .hardware import HardwareManager
from .model_resources import accelerator_api_requirements, gpu_vendor_requirement, number_or_none
from .models import Profile
from .profile_archive import load_profile_archive, snapshot_profile
from .runtime_evidence import artifact_lock


COMPARISON_SCHEMA_VERSION = "1.0"
CLASSIFICATIONS = {"exact", "capability_equivalent", "materially_incompatible", "unresolved"}
_HARDWARE_FILE = "hardware.yaml"


def compare_profile_sources(
    left: str,
    right: str,
    *,
    left_source: str = "profile",
    right_source: str = "profile",
    profiles_dir: Path | str | None = None,
) -> dict[str, Any]:
    lhs = _load_source(left, left_source, profiles_dir)
    rhs = _load_source(right, right_source, profiles_dir)
    left_docs, right_docs = _documents(lhs["archive"]), _documents(rhs["archive"])
    paths = sorted(set(left_docs) | set(right_docs))
    semantic_changes = [path for path in paths if left_docs.get(path) != right_docs.get(path)]
    byte_changes = _byte_changes(lhs["archive"], rhs["archive"])
    left_locks = _artifact_locks(left_docs.get("models.yaml", {}))
    right_locks = _artifact_locks(right_docs.get("models.yaml", {}))
    result = {
        "name": "profile_comparison",
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "left": _source_summary(lhs),
        "right": _source_summary(rhs),
        "canonical_equal": not semantic_changes,
        "byte_equal": not byte_changes,
        "changes": [],
        "evidence": {
            "semantic_changed_files": semantic_changes,
            "byte_changed_files": byte_changes,
            "artifact_locks": {"left": left_locks, "right": right_locks},
            "comparison_basis": [
                "validated portable archive manifests",
                "parsed canonical portable YAML evidence",
                "selected-model minimum resource, GPU-vendor, and accelerator-API requirements",
            ],
        },
    }
    if not semantic_changes:
        return _finish(result, "exact", "portable profile evidence is canonically identical", True)

    if any(path != _HARDWARE_FILE for path in semantic_changes):
        result["changes"] = [_file_change(path, lhs, rhs, "material") for path in semantic_changes]
        return _finish(
            result,
            "materially_incompatible",
            "portable model, runtime, provider, target, policy, or environment configuration changed",
            False,
        )

    left_hardware, right_hardware = left_docs[_HARDWARE_FILE], right_docs[_HARDWARE_FILE]
    if _hardware_controls(left_hardware) != _hardware_controls(right_hardware):
        result["changes"] = [_file_change(_HARDWARE_FILE, lhs, rhs, "material")]
        return _finish(
            result,
            "materially_incompatible",
            "hardware controls or managed-machine configuration changed beyond the active machine selection",
            False,
        )

    left_facts = _configured_machine_facts(left_hardware)
    right_facts = _configured_machine_facts(right_hardware)
    result["changes"] = _fact_changes(left_facts, right_facts, lhs, rhs)
    if not result["changes"]:
        result["changes"] = [_file_change(_HARDWARE_FILE, lhs, rhs, "non_active_variance")]
    selected = _selected_models(left_docs.get("models.yaml", {}))
    result["evidence"].update(
        selected_models=selected,
        left_hardware=left_facts,
        right_hardware=right_facts,
    )
    if not selected:
        return _finish(
            result,
            "unresolved",
            "active hardware differs but no selected models provide a capability-equivalence basis",
            None,
        )

    left_fit = _evaluate_models(left_docs["models.yaml"], selected, left_facts)
    right_fit = _evaluate_models(right_docs["models.yaml"], selected, right_facts)
    result["evidence"].update(left_fit=left_fit, right_fit=right_fit)
    if _has_state(left_fit, "fail") or _has_state(right_fit, "fail"):
        return _finish(
            result,
            "materially_incompatible",
            "at least one active machine does not meet a selected local model's minimum requirements",
            False,
        )
    if _has_state(left_fit, "unresolved") or _has_state(right_fit, "unresolved"):
        return _finish(
            result,
            "unresolved",
            "available profile evidence is insufficient to prove selected-model capability equivalence",
            None,
        )
    return _finish(
        result,
        "capability_equivalent",
        "active machine facts differ, but both satisfy every selected model's minimum requirements",
        True,
    )


def check_profile_replays(
    source: str,
    client_archives: list[str],
    *,
    source_type: str = "profile",
    profiles_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Compare one approved source with archives produced by multiple client installations."""
    resolved = [str(Path(value).expanduser().resolve()) for value in client_archives]
    if len(resolved) < 2:
        raise ValueError("replay check requires at least two --client-archive values")
    if len(set(resolved)) != len(resolved):
        raise ValueError("replay check client archives must be distinct")

    comparisons = [
        compare_profile_sources(
            source,
            path,
            left_source=source_type,
            right_source="archive",
            profiles_dir=profiles_dir,
        )
        for path in sorted(resolved)
    ]
    clients = [
        {
            "archive": comparison["right"]["label"],
            "profile": comparison["right"]["profile"],
            "canonical_sha256": comparison["right"]["canonical_sha256"],
            "classification": comparison["classification"],
            "equivalent": comparison["equivalent"],
            "summary": comparison["summary"],
            "changes": comparison["changes"],
            "evidence": comparison["evidence"],
            "provenance": comparison["right"]["provenance"],
        }
        for comparison in comparisons
    ]
    counts = {classification: 0 for classification in sorted(CLASSIFICATIONS)}
    for client in clients:
        counts[str(client["classification"])] += 1
    if counts["materially_incompatible"]:
        overall = "materially_incompatible"
    elif counts["unresolved"]:
        overall = "unresolved"
    elif counts["capability_equivalent"]:
        overall = "capability_equivalent"
    else:
        overall = "exact"
    replay_ready = all(client["equivalent"] is True for client in clients)
    return {
        "name": "profile_replay_check",
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "read_only": True,
        "source": comparisons[0]["left"],
        "client_count": len(clients),
        "clients": clients,
        "counts": counts,
        "classification": overall,
        "replay_ready": replay_ready,
        "summary": (
            "every client archive reproduces compatible approved profile evidence"
            if replay_ready
            else "one or more client archives are unresolved or materially incompatible"
        ),
    }


def assess_profile_drift(
    source: str,
    *,
    source_type: str = "profile",
    profiles_dir: Path | str | None = None,
    current_discovery: dict[str, Any] | None = None,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    snapshot = _load_source(source, source_type, profiles_dir)
    docs = _documents(snapshot["archive"])
    expected = _configured_machine_facts(docs.get(_HARDWARE_FILE, {}))
    if current_discovery is None:
        current_discovery = HardwareManager(
            _profile_from_documents(snapshot, docs),
            command_runner=command_runner,
        ).discover()
    current = _discovered_machine_facts(current_discovery)
    current_source = {"label": "current_machine", "kind": "current_machine"}
    result = {
        "name": "profile_machine_drift",
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "profile": _source_summary(snapshot),
        "current_machine": {"kind": "current_machine", "provenance": "live hardware discovery"},
        "changes": _fact_changes(expected, current, snapshot, current_source),
        "evidence": {
            "profile_hardware": expected,
            "current_hardware": current,
            "comparison_basis": [
                "explicit active profile hardware facts",
                "live current-machine discovery",
                "selected-model minimum resource, GPU-vendor, and accelerator-API requirements",
            ],
        },
    }
    explicit = {key: value for key, value in expected.items() if value is not None}
    if explicit and all(current.get(key) == value for key, value in explicit.items()):
        return _finish(
            result,
            "exact",
            "all explicitly configured profile hardware facts match the current machine",
            True,
        )

    selected = _selected_models(docs.get("models.yaml", {}))
    result["evidence"]["selected_models"] = selected
    if not selected:
        return _finish(
            result,
            "unresolved",
            "hardware differs or is automatic, and no selected models provide a capability basis",
            None,
        )
    current_fit = _evaluate_models(docs["models.yaml"], selected, current)
    result["evidence"]["current_fit"] = current_fit
    if _has_state(current_fit, "fail"):
        return _finish(
            result,
            "materially_incompatible",
            "the current machine does not meet a selected local model's minimum requirements",
            False,
        )
    if _has_state(current_fit, "unresolved"):
        return _finish(
            result,
            "unresolved",
            "current-machine evidence is insufficient to prove selected-model capability equivalence",
            None,
        )
    return _finish(
        result,
        "capability_equivalent",
        "current hardware differs but satisfies every selected model's minimum requirements",
        True,
    )


def _load_source(value: str, source_type: str, profiles_dir: Path | str | None) -> dict[str, Any]:
    if source_type == "profile":
        archive, label = snapshot_profile(value, profiles_dir=profiles_dir), value
    elif source_type == "archive":
        path = Path(value).expanduser().resolve()
        archive, label = load_profile_archive(path), str(path)
    else:
        raise ValueError("profile source type must be profile or archive")
    return {
        "label": label,
        "kind": source_type,
        "archive": archive,
        "canonical_sha256": _canonical_digest(_documents(archive)),
    }


def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
    archive = source["archive"]
    return {
        "kind": source["kind"],
        "label": source["label"],
        "profile": archive["profile"],
        "canonical_sha256": source["canonical_sha256"],
        "manifest": archive["manifest"]["included"],
        "provenance": (
            f"editable profile {source['label']}"
            if source["kind"] == "profile"
            else f"validated portable archive {source['label']}"
        ),
    }


def _documents(archive: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["path"]: parse_yaml(entry["content"]) for entry in archive["files"]}


def _byte_changes(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    lhs = {entry["path"]: entry["sha256"] for entry in left["files"]}
    rhs = {entry["path"]: entry["sha256"] for entry in right["files"]}
    return sorted(path for path in set(lhs) | set(rhs) if lhs.get(path) != rhs.get(path))


def _hardware_controls(config: dict[str, Any]) -> dict[str, Any]:
    ignored = {"active", "selected", "hardware_profiles", "machine_schema"}
    return {key: value for key, value in config.items() if key not in ignored}


def _active_values(config: dict[str, Any]) -> dict[str, Any]:
    selected = config.get("selected")
    if isinstance(selected, dict) and isinstance(selected.get("values"), dict):
        return selected["values"]
    active, templates = str(config.get("active") or ""), config.get("hardware_profiles")
    if isinstance(templates, dict) and isinstance(templates.get(active), dict):
        return templates[active]
    return {}


def _configured_machine_facts(config: dict[str, Any]) -> dict[str, Any]:
    values = _active_values(config)
    ram, unified = _number(values.get("memory_gb")), _number(values.get("unified_memory_gb"))
    return {
        "cpu_architecture": _text(values.get("cpu_architecture")),
        "cpu_cores": _number(values.get("cpu_cores", values.get("cpu"))),
        "cpu_threads": _number(values.get("cpu_threads")),
        "ram_gb": ram if ram is not None else unified,
        "unified_memory_gb": unified,
        "gpu_vendor": _text(values.get("gpu_vendor", values.get("vendor"))),
        "gpu_model": _text(values.get("gpu_model", values.get("gpu"))),
        "gpu_count": _number(values.get("gpu_count")),
        "vram_gb": _number(values.get("vram_gb")),
        "total_vram_gb": _number(values.get("total_vram_gb")),
        "accelerator_apis": _strings(values.get("accelerator_apis")) or None,
        "os": _text(values.get("os")),
    }


def _discovered_machine_facts(discovered: dict[str, Any]) -> dict[str, Any]:
    gpus = [row for row in discovered.get("gpus", []) if isinstance(row, dict)]
    vendors = sorted({str(row.get("vendor") or "").lower() for row in gpus if row.get("vendor")})
    vendor = vendors[0] if len(vendors) == 1 else ("mixed" if vendors else "none")
    vrams = [float(row["vram_mb"]) / 1024 for row in gpus if number_or_none(row.get("vram_mb")) is not None]
    api_map = {"nvidia": ["cuda"], "amd": ["rocm"], "apple": ["metal"], "intel": ["openvino"]}
    support = discovered.get("platform_support")
    os_name = (
        str(support.get("os")).lower() if isinstance(support, dict) and support.get("os") else platform.system().lower()
    )
    return {
        "cpu_architecture": _text(discovered.get("machine")),
        "cpu_cores": _number(discovered.get("cpu_count")),
        "cpu_threads": _number(discovered.get("cpu_count")),
        "ram_gb": _number(discovered.get("memory_gb")),
        "unified_memory_gb": _number(discovered.get("unified_memory_gb")),
        "gpu_vendor": vendor,
        "gpu_model": _text(gpus[0].get("name")) if len(gpus) == 1 and gpus[0].get("name") else None,
        "gpu_count": float(len(gpus)),
        "vram_gb": max(vrams) if vrams else 0.0,
        "total_vram_gb": sum(vrams) if vrams else 0.0,
        "accelerator_apis": api_map.get(vendor, ["cpu"] if vendor == "none" else []),
        "os": os_name,
    }


def _selected_models(config: dict[str, Any]) -> list[str]:
    defaults = config.get("defaults")
    if not isinstance(defaults, dict):
        return []
    return sorted({value for value in defaults.values() if isinstance(value, str) and value})


def _evaluate_models(config: dict[str, Any], aliases: list[str], facts: dict[str, Any]) -> list[dict[str, Any]]:
    models = config.get("models")
    models = models if isinstance(models, dict) else {}
    results: list[dict[str, Any]] = []
    for alias in aliases:
        model, provenance = models.get(alias), f"models.yaml#/models/{alias}"
        if not isinstance(model, dict):
            results.append(
                {
                    "alias": alias,
                    "state": "unresolved",
                    "reason": "selected alias is absent from the portable model catalog",
                    "provenance": provenance,
                }
            )
            continue
        if not bool(model.get("local", False)):
            results.append(
                {
                    "alias": alias,
                    "state": "pass",
                    "reason": "managed or remote model does not consume local inference resources",
                    "provenance": provenance,
                }
            )
            continue
        blockers: list[str] = []
        unknown: list[str] = []
        ram, vram = _number(facts.get("ram_gb")), _number(facts.get("vram_gb"))
        min_ram, min_vram = number_or_none(model.get("min_ram_gb")), number_or_none(model.get("min_vram_gb"))
        if min_ram is not None:
            if ram is None:
                unknown.append("RAM is unknown")
            elif ram < min_ram:
                blockers.append(f"RAM {ram:g}GB is below minimum {min_ram:g}GB")
        if min_vram is not None and min_vram > 0:
            if vram is None:
                unknown.append("VRAM is unknown")
            elif vram < min_vram:
                blockers.append(f"VRAM {vram:g}GB is below minimum {min_vram:g}GB")
        required_vendor, available_vendor = gpu_vendor_requirement(model), str(facts.get("gpu_vendor") or "").lower()
        if required_vendor not in {"generic", "none", "cpu"}:
            if not available_vendor:
                unknown.append("GPU vendor is unknown")
            elif required_vendor == "mixed" and available_vendor in {"none", "cpu"}:
                blockers.append(f"GPU vendor {available_vendor} does not meet mixed GPU requirement")
            elif required_vendor != "mixed" and available_vendor != required_vendor:
                blockers.append(f"GPU vendor {available_vendor} does not meet {required_vendor} requirement")
        required_apis = accelerator_api_requirements(model)
        available_apis = set(_strings(facts.get("accelerator_apis")))
        if required_apis:
            if not available_apis:
                unknown.append("accelerator APIs are unknown")
            elif not available_apis.intersection(required_apis):
                blockers.append(
                    f"accelerator APIs {sorted(available_apis)} do not include any required API {sorted(required_apis)}"
                )
        state = "fail" if blockers else ("unresolved" if unknown else "pass")
        results.append(
            {
                "alias": alias,
                "model": model.get("model") or alias,
                "state": state,
                "reason": "; ".join(blockers or unknown or ["minimum local capability requirements are satisfied"]),
                "requirements": {
                    "min_ram_gb": min_ram,
                    "min_vram_gb": min_vram,
                    "gpu_vendor": required_vendor,
                    "accelerator_apis": required_apis,
                },
                "provenance": provenance,
            }
        )
    return results


def _profile_from_documents(snapshot: dict[str, Any], docs: dict[str, dict[str, Any]]) -> Profile:
    archive = snapshot["archive"]
    return Profile(
        name=str(archive["profile"]),
        root=Path(snapshot["label"]),
        workspace=Path.cwd().resolve(),
        hardware=docs.get("hardware.yaml", {}),
        backends=docs.get("backends.yaml", {}),
        repository=docs.get("repository.yaml", {}),
        tools=docs.get("tools.yaml", {}),
        approvals=docs.get("approvals.yaml", {}),
        environment=docs.get("environment.yaml", {}),
        models=docs.get("models.yaml", {}),
        targets=docs.get("targets.yaml", {}),
        orchestrators=docs.get("orchestrators.yaml", {}),
    )


def _file_change(path: str, left: dict[str, Any], right: dict[str, Any], impact: str) -> dict[str, Any]:
    return {
        "path": path,
        "impact": impact,
        "left_provenance": f"{left['kind']}:{left['label']}#{path}",
        "right_provenance": f"{right['kind']}:{right['label']}#{path}",
        "reason": "canonical portable document differs",
    }


def _fact_changes(
    left: dict[str, Any], right: dict[str, Any], lhs: dict[str, Any], rhs: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "path": f"hardware.{key}",
            "left": left.get(key),
            "right": right.get(key),
            "impact": "capability_evidence",
            "left_provenance": f"{lhs['kind']}:{lhs['label']}#hardware.yaml",
            "right_provenance": f"{rhs['kind']}:{rhs['label']}#hardware",
            "reason": "active machine fact differs",
        }
        for key in sorted(set(left) | set(right))
        if left.get(key) != right.get(key)
    ]


def _finish(result: dict[str, Any], classification: str, summary: str, equivalent: bool | None) -> dict[str, Any]:
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"unsupported profile comparison classification: {classification}")
    result.update(classification=classification, equivalent=equivalent, summary=summary)
    return result


def _has_state(rows: list[dict[str, Any]], state: str) -> bool:
    return any(row.get("state") == state for row in rows)


def _canonical_digest(documents: dict[str, dict[str, Any]]) -> str:
    serialized = json.dumps(documents, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _number(value: Any) -> float | None:
    return None if isinstance(value, bool) else number_or_none(value)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in {"auto", "provider_defined", "none_or_auto"}:
        return None
    if "-" in text and any(char.isdigit() for char in text):
        return None
    return text


def _strings(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return []


def _artifact_locks(models_document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(models_document, dict):
        return {}
    models = models_document.get("models", {})
    providers = models_document.get("providers", {})
    if not isinstance(models, dict):
        return {}
    provider_rows = providers if isinstance(providers, dict) else {}
    locks: dict[str, dict[str, Any]] = {}
    for name, value in sorted(models.items()):
        if not isinstance(value, dict):
            continue
        provider = provider_rows.get(str(value.get("provider") or ""), {})
        provider_ownership = provider.get("ownership") if isinstance(provider, dict) else None
        if str(value.get("ownership") or provider_ownership or "self_managed") == "managed_service":
            continue
        locks[str(name)] = artifact_lock(str(name), value)
    return locks
