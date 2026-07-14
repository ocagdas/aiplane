from __future__ import annotations

from copy import deepcopy
import json
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
            "path": "1$schema",
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
    return findings
