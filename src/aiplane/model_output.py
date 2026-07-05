from __future__ import annotations

from typing import Any

from .runtime_catalog import RuntimeCatalog
from .models import Profile


def group_rows(
    rows: list[dict[str, object]], key: str
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        value = row.get(key) or "unknown"
        grouped.setdefault(str(value), []).append(row)
    return {
        name: sorted(
            items, key=lambda item: str(item.get("name") or item.get("role") or "")
        )
        for name, items in sorted(grouped.items())
    }


def group_model_rows(
    profile: Profile, rows: list[dict[str, Any]], group_by: str
) -> dict[str, object]:
    runtime_catalog = RuntimeCatalog(profile)
    models = runtime_catalog._models()
    grouped: dict[str, object] = {}
    for row in rows:
        name = str(row.get("name"))
        model = models.get(name, {})
        if group_by == "source":
            keys = [runtime_catalog.source_for_model(model)]
        elif group_by == "runtime":
            keys = runtime_catalog.supported_runtimes(name) or ["no_runtime"]
        elif group_by == "model":
            keys = [str(row.get("model") or "unknown")]
        elif group_by == "provider-kind":
            ownership = str(row.get("ownership") or "unknown")
            provider = str(row.get("provider") or "unknown")
            ownership_group = grouped.setdefault(ownership, {})
            if isinstance(ownership_group, dict):
                ownership_group.setdefault(provider, []).append(row)
            continue
        else:
            keys = [str(row.get(group_by) or "unknown")]
        for key in keys:
            grouped.setdefault(key, []).append(row)
    if group_by == "provider-kind":
        return {
            "group_by": group_by,
            "groups": {
                ownership: {
                    provider: sorted(
                        items, key=lambda item: str(item.get("name") or "")
                    )
                    for provider, items in sorted(providers.items())
                    if isinstance(items, list)
                }
                for ownership, providers in sorted(grouped.items())
                if isinstance(providers, dict)
            },
        }
    return {
        "group_by": group_by,
        "groups": {key: value for key, value in sorted(grouped.items())},
    }
