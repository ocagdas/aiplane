"""Versioned maintenance promises for public adapters and clients."""

from __future__ import annotations

from typing import Any

from .integration_contracts import ALL_INTEGRATION_TOOLS, TIER1_EXPORT_TOOL_SET
from .runtime_definitions import RUNTIME_DEFINITIONS, SOURCE_DEFINITIONS

SUPPORT_CATALOG_VERSION = "1.0"


def support_catalog() -> dict[str, Any]:
    runtimes = {
        name: _record(
            name,
            "runtime",
            _runtime_tier(name, definition),
            _runtime_capabilities(name, definition),
            _runtime_limitations(name, definition),
        )
        for name, definition in sorted(RUNTIME_DEFINITIONS.items())
    }
    providers = {
        name: _record(
            name,
            "provider",
            "tier_1" if definition.get("catalog_adapter") != "profile_catalog" else "tier_2",
            ["profile_catalog", str(definition.get("catalog_adapter", "profile_catalog"))],
            [] if definition.get("catalog_adapter") != "profile_catalog" else ["manual catalog entries"],
        )
        for name, definition in sorted(SOURCE_DEFINITIONS.items())
    }
    clients = {
        name: _record(
            name,
            "client",
            "tier_1" if name in TIER1_EXPORT_TOOL_SET else "tier_2",
            ["deterministic_export"],
            ["configuration export only; client installation and execution remain external"],
        )
        for name in sorted(ALL_INTEGRATION_TOOLS)
    }
    return {
        "schema_version": SUPPORT_CATALOG_VERSION,
        "tiers": {
            "tier_1": "maintained public contract with regression coverage",
            "tier_2": "maintained best-effort integration with narrower coverage",
            "experimental": "usable preview; contract may change",
            "planned": "known target; not an implementation claim",
        },
        "maintenance": {
            "owner": "aiplane maintainers",
            "expectation": "regression tests and documentation are updated with behavior changes",
            "version_policy": "upstream versions are recorded only when verified; an omitted version is not a compatibility claim",
        },
        "runtimes": runtimes,
        "providers": providers,
        "clients": clients,
    }


def support_records(kind: str | None = None) -> list[dict[str, Any]]:
    catalog = support_catalog()
    groups = [kind] if kind else ["runtime", "provider", "client"]
    result: list[dict[str, Any]] = []
    for group in groups:
        key = f"{group}s"
        if key not in catalog:
            raise ValueError(f"unknown support kind: {group}")
        result.extend(catalog[key].values())
    return sorted(result, key=lambda item: (item["kind"], item["name"]))


def support_record(kind: str, name: str) -> dict[str, Any]:
    records = {item["name"]: item for item in support_records(kind)}
    if name not in records:
        raise ValueError(f"unknown {kind}: {name}")
    return records[name]


def _record(name: str, kind: str, tier: str, capabilities: list[str], limitations: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "support_tier": tier,
        "catalog_version": SUPPORT_CATALOG_VERSION,
        "upstream_versions": [],
        "owner": "aiplane maintainers",
        "maintenance_expectation": "behavior changes require contract tests and documentation",
        "capabilities": sorted(set(capabilities)),
        "limitations": limitations,
    }


def _runtime_tier(name: str, definition: dict[str, Any]) -> str:
    if name in {"ollama", "docker_model_runner", "vllm"}:
        return "tier_1"
    managed = definition.get("managed_by_helper")
    if managed is True or managed == "partial":
        return "tier_2"
    return "planned" if managed == "planned" else "experimental"


def _runtime_capabilities(name: str, definition: dict[str, Any]) -> list[str]:
    capabilities = ["catalog_mapping", "fit_assessment", "health"]
    if definition.get("protocol") in {"openai_compatible", "ollama_api"}:
        capabilities.append("endpoint_export")
    if definition.get("managed_by_helper") in {True, "partial"} or name == "docker_model_runner":
        capabilities.append("guarded_lifecycle")
    if name == "docker_model_runner":
        capabilities.extend(["installed_inventory", "native_identity", "benchmark"])
    return capabilities


def _runtime_limitations(name: str, definition: dict[str, Any]) -> list[str]:
    if name == "docker_model_runner":
        return ["requires a Docker installation that includes the docker model command"]
    if definition.get("gui_required"):
        return ["runtime setup is managed by its desktop application"]
    if definition.get("managed_by_helper") == "planned":
        return ["lifecycle automation is not implemented"]
    return []
