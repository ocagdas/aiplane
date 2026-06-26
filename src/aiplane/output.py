from __future__ import annotations

import json
from typing import Any

JSON_KEY_ORDER = [
    "name",
    "default",
    "root",
    "workspace",
    "selected",
    "role",
    "orchestrator",
    "runtime",
    "model",
    "provider",
    "supported_providers",
    "supported_orchestrators",
    "preferred_runtime",
    "suitable_runtimes",
    "supported_runtimes",
    "capability_avg_score",
    "level",
    "source",
    "ownership",
    "refresh_status",
    "provider_visible",
    "local_presence",
    "type",
    "enabled",
    "min_ram_gb",
    "recommended_ram_gb",
    "min_vram_gb",
    "recommended_vram_gb",
    "exists",
    "local",
    "available",
    "status",
    "reason",
    "description",
    "endpoint",
    "api_key_env",
    "group_by",
    "changes",
    "catalog",
    "groups",
    "defaults",
    "machine",
    "results",
    "models",
    "runtimes",
    "providers",
    "config",
    "settings",
    "effective",
    "path",
    "notes",
]


def ordered_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [ordered_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    ordered: dict[Any, Any] = {}
    for key in JSON_KEY_ORDER:
        if key in value:
            ordered[key] = ordered_json_value(value[key])
    for key, item in value.items():
        if key not in ordered:
            ordered[key] = ordered_json_value(item)
    return ordered


def json_dumps(value: Any, indent: int | None = None, sort_keys: bool | None = None) -> str:
    return json.dumps(ordered_json_value(value), indent=indent)
