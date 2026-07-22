from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
from typing import Any

from .config import CONFIG_FILES, resource_root
from .models import Profile

PROFILE_SCHEMA_VERSION = "1.0"
PROFILE_SCHEMA_ID = "https://aiplane.dev/schemas/profile/v1"


def profile_schema_path() -> Path:
    return resource_root() / "schemas" / "aiplane-profile-v1.schema.json"


def load_profile_schema() -> dict[str, Any]:
    return json.loads(profile_schema_path().read_text(encoding="utf-8"))


def canonical_profile(profile: Profile) -> dict[str, Any]:
    document: dict[str, Any] = {
        "$schema": PROFILE_SCHEMA_ID,
        "schema_version": PROFILE_SCHEMA_VERSION,
        "name": profile.name,
    }
    for key in CONFIG_FILES:
        document[key] = deepcopy(getattr(profile, key))
    return document


def merge_profile_documents(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge canonical profile documents: mappings recurse; every other value replaces."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_profile_documents(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def structural_profile_findings(document: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = [
        {
            "name": "schema:id",
            "path": "$.$schema",
            "ok": document.get("$schema") == PROFILE_SCHEMA_ID,
            "detail": str(document.get("$schema") or "missing"),
            "remediation": f"Set $schema to {PROFILE_SCHEMA_ID} in the canonical document.",
        }
    ]
    version = document.get("schema_version")
    findings.append(
        {
            "name": "schema:version",
            "path": "$.schema_version",
            "ok": version == PROFILE_SCHEMA_VERSION,
            "detail": str(version),
            "remediation": f"Set schema_version to {PROFILE_SCHEMA_VERSION} in the canonical document.",
        }
    )
    for key in ("name", *CONFIG_FILES):
        value = document.get(key)
        expected = str if key == "name" else dict
        findings.append(
            {
                "name": f"schema:{key}",
                "path": f"$.{key}",
                "ok": isinstance(value, expected) and (key != "name" or bool(value)),
                "detail": type(value).__name__ if value is not None else "missing",
                "remediation": (
                    "Set a non-empty profile name."
                    if key == "name"
                    else f"Restore {CONFIG_FILES[key]} with `aiplane profiles repair PROFILE --file {CONFIG_FILES[key]}`."
                ),
            }
        )
    findings.extend(_model_contract_findings(document))
    return findings


_MODEL_NUMBER_FIELDS = (
    "min_ram_gb",
    "recommended_ram_gb",
    "min_vram_gb",
    "recommended_vram_gb",
    "parameters_b",
)
_MODEL_LIST_FIELDS = ("roles", "supported_runtimes", "required_accelerator_apis")


def _model_contract_findings(document: dict[str, Any]) -> list[dict[str, Any]]:
    config = document.get("models")
    if not isinstance(config, dict):
        return []
    findings: list[dict[str, Any]] = []
    defaults = config.get("defaults")
    findings.append(
        {
            "name": "contract:models_defaults",
            "path": "$.models.defaults",
            "ok": isinstance(defaults, dict),
            "detail": type(defaults).__name__ if defaults is not None else "missing",
            "remediation": "Set models.yaml defaults to a mapping of role names to model aliases or null.",
        }
    )
    catalog = config.get("models")
    findings.append(
        {
            "name": "contract:models_catalog",
            "path": "$.models.models",
            "ok": isinstance(catalog, dict),
            "detail": type(catalog).__name__ if catalog is not None else "missing",
            "remediation": "Set models.yaml models to a mapping of aliases to model definitions.",
        }
    )
    if not isinstance(catalog, dict):
        return findings
    for alias, value in sorted(catalog.items(), key=lambda item: str(item[0])):
        path = f"$.models.models.{alias}"
        if not isinstance(value, dict):
            findings.append(
                {
                    "name": f"contract:model:{alias}",
                    "path": path,
                    "ok": False,
                    "detail": type(value).__name__,
                    "remediation": f"Set model alias {alias!r} to a mapping in models.yaml.",
                }
            )
            continue
        for field in ("model", "provider"):
            field_value = value.get(field)
            findings.append(
                {
                    "name": f"contract:model_{field}:{alias}",
                    "path": f"{path}.{field}",
                    "ok": isinstance(field_value, str) and bool(field_value.strip()),
                    "detail": str(field_value if field_value is not None else "missing"),
                    "remediation": f"Set a non-empty {field} for model alias {alias!r} in models.yaml.",
                }
            )
        for field in ("enabled", "local"):
            if field not in value:
                continue
            findings.append(
                {
                    "name": f"contract:model_{field}:{alias}",
                    "path": f"{path}.{field}",
                    "ok": isinstance(value[field], bool),
                    "detail": type(value[field]).__name__,
                    "remediation": f"Set {field} to true or false for model alias {alias!r}.",
                }
            )
        for field in _MODEL_NUMBER_FIELDS:
            if field not in value:
                continue
            number = value[field]
            valid = (
                isinstance(number, (int, float))
                and not isinstance(number, bool)
                and math.isfinite(float(number))
                and float(number) >= 0
            )
            findings.append(
                {
                    "name": f"contract:model_{field}:{alias}",
                    "path": f"{path}.{field}",
                    "ok": valid,
                    "detail": str(number),
                    "remediation": f"Set {field} to a finite non-negative number for model alias {alias!r}.",
                }
            )
        for field in _MODEL_LIST_FIELDS:
            if field not in value:
                continue
            items = value[field]
            valid = (
                isinstance(items, list)
                and all(isinstance(item, str) and bool(item.strip()) for item in items)
                and len(items) == len(set(items))
            )
            findings.append(
                {
                    "name": f"contract:model_{field}:{alias}",
                    "path": f"{path}.{field}",
                    "ok": valid,
                    "detail": str(items),
                    "remediation": f"Set {field} to a duplicate-free list of non-empty strings for model alias {alias!r}.",
                }
            )
        for minimum, recommended in (
            ("min_ram_gb", "recommended_ram_gb"),
            ("min_vram_gb", "recommended_vram_gb"),
        ):
            left, right = value.get(minimum), value.get(recommended)
            if not all(
                isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(float(item))
                for item in (left, right)
            ):
                continue
            findings.append(
                {
                    "name": f"contract:model_{recommended}_order:{alias}",
                    "path": f"{path}.{recommended}",
                    "ok": float(right) >= float(left),
                    "detail": f"{recommended}={right}; {minimum}={left}",
                    "remediation": f"Set {recommended} greater than or equal to {minimum} for model alias {alias!r}.",
                }
            )
    return findings
