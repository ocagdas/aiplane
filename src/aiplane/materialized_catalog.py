from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .persistence import atomic_write_text


CATALOG_CACHE_SCHEMA_VERSION = "1.0"
CATALOG_ENRICHMENT_VERSION = "1"
CATALOG_CACHE_RELATIVE_PATH = Path(".aiplane/cache/model-catalog-v1.json")

_SENSITIVE_PROPERTY_PARTS = {
    "api_key",
    "authorization",
    "connection_string",
    "credential",
    "password",
    "secret",
    "token",
}

_MEMORY_CACHE: dict[tuple[Path, int, int], dict[str, Any]] = {}


def clear_materialized_memory_cache() -> None:
    _MEMORY_CACHE.clear()


class MaterializedCatalog:
    """A disposable, query-ready projection of profile and discovered model data."""

    def __init__(self, profile_root: Path):
        self.path = profile_root / CATALOG_CACHE_RELATIVE_PATH

    def input_digest(
        self,
        curated_config: Mapping[str, Any],
        generated_path: Path,
        benchmark_root: Path,
    ) -> str:
        digest = hashlib.sha256()
        digest.update(CATALOG_CACHE_SCHEMA_VERSION.encode())
        digest.update(CATALOG_ENRICHMENT_VERSION.encode())
        relevant = {
            "models": curated_config.get("models", {}),
            "providers": curated_config.get("providers", {}),
        }
        digest.update(_canonical_json(relevant).encode())
        _update_file_digest(digest, generated_path)
        if benchmark_root.is_dir():
            for benchmark in sorted(benchmark_root.glob("*.json"), key=lambda item: item.name):
                _update_file_digest(digest, benchmark)
        return digest.hexdigest()

    def load(self, expected_digest: str) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            stat = self.path.stat()
            key = (self.path.resolve(), stat.st_mtime_ns, stat.st_size)
            payload = _MEMORY_CACHE.get(key)
            if payload is None:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    return None
                payload = loaded
                _MEMORY_CACHE.clear()
                _MEMORY_CACHE[key] = payload
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if payload.get("schema_version") != CATALOG_CACHE_SCHEMA_VERSION:
            return None
        if payload.get("enrichment_version") != CATALOG_ENRICHMENT_VERSION:
            return None
        if payload.get("input_digest") != expected_digest:
            return None
        if not isinstance(payload.get("generated_at"), str) or not payload["generated_at"].strip():
            return None
        if not isinstance(payload.get("rows"), list) or not isinstance(payload.get("indexes"), dict):
            return None
        return payload

    def write(self, rows: Iterable[Mapping[str, Any]], input_digest: str) -> dict[str, Any]:
        payload = self.build_payload(rows, input_digest)
        atomic_write_text(self.path, json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        stat = self.path.stat()
        _MEMORY_CACHE.clear()
        _MEMORY_CACHE[(self.path.resolve(), stat.st_mtime_ns, stat.st_size)] = payload
        return payload

    def clear(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        _MEMORY_CACHE.clear()
        return True

    @staticmethod
    def build_payload(rows: Iterable[Mapping[str, Any]], input_digest: str) -> dict[str, Any]:
        materialized_rows = [dict(row) for row in rows]
        indexes: dict[str, Any] = {
            "name": {},
            "model": {},
            "provider": {},
            "source": {},
            "runtime": {},
            "role": {},
            "ownership": {},
            "enabled": {},
            "score_source": {},
            "property": {},
        }
        for position, row in enumerate(materialized_rows):
            _add_index(indexes["name"], row.get("name"), position)
            _add_index(indexes["model"], row.get("model"), position)
            _add_index(indexes["provider"], row.get("provider"), position)
            _add_index(indexes["source"], row.get("source"), position)
            _add_index(indexes["ownership"], row.get("ownership"), position)
            _add_index(indexes["enabled"], bool(row.get("enabled", True)), position)
            capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
            _add_index(indexes["score_source"], capabilities.get("score_source"), position)
            runtimes = row.get("supported_runtimes") if isinstance(row.get("supported_runtimes"), list) else []
            for runtime in runtimes:
                _add_index(indexes["runtime"], runtime, position)
            roles = row.get("roles") if isinstance(row.get("roles"), list) else []
            for role in roles:
                _add_index(indexes["role"], role, position)
            properties = row.get("_properties") if isinstance(row.get("_properties"), dict) else {}
            for property_path, value in _property_values(properties):
                path_index = indexes["property"].setdefault(property_path, {})
                _add_index(path_index, value, position)
        return {
            "schema_version": CATALOG_CACHE_SCHEMA_VERSION,
            "enrichment_version": CATALOG_ENRICHMENT_VERSION,
            "input_digest": input_digest,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(materialized_rows),
            "rows": materialized_rows,
            "indexes": indexes,
        }

    @staticmethod
    def candidate_rows(payload: Mapping[str, Any], filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        indexes = payload.get("indexes") if isinstance(payload.get("indexes"), dict) else {}
        candidates: list[set[int]] = []
        for filter_name, index_name in (
            ("name", "name"),
            ("model", "model"),
            ("provider", "provider"),
            ("source", "source"),
            ("runtime", "runtime"),
            ("ownership", "ownership"),
            ("score_source", "score_source"),
        ):
            value = filters.get(filter_name)
            if value is not None:
                candidates.append(_index_positions(indexes, index_name, value))
        if filters.get("enabled_only"):
            candidates.append(_index_positions(indexes, "enabled", True))
        roles = _string_list(filters.get("roles") or filters.get("role"))
        if roles:
            role_positions: set[int] = set()
            for role in roles:
                role_positions.update(_index_positions(indexes, "role", role))
            candidates.append(role_positions)
        property_filters = filters.get("properties") if isinstance(filters.get("properties"), dict) else {}
        property_indexes = indexes.get("property") if isinstance(indexes.get("property"), dict) else {}
        for property_path, expected in property_filters.items():
            path_index = property_indexes.get(str(property_path))
            if isinstance(path_index, dict):
                candidates.append(set(path_index.get(_index_key(expected), [])))
        selected = set(range(len(rows))) if not candidates else set.intersection(*candidates)
        return [dict(rows[position]) for position in sorted(selected)]


def materialized_metadata(
    path: Path,
    payload: Mapping[str, Any],
    *,
    rebuilt: bool,
    persisted: bool,
    error: str | None = None,
) -> dict[str, Any]:
    result = {
        "path": str(path),
        "schema_version": payload.get("schema_version"),
        "input_digest": payload.get("input_digest"),
        "generated_at": payload.get("generated_at"),
        "rows": payload.get("row_count", len(payload.get("rows", []))),
        "rebuilt": rebuilt,
        "persisted": persisted,
        "current": True,
    }
    if error:
        result["error"] = error
    return result


def safe_catalog_properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in properties.items():
        normalized = str(key).strip().lower().replace("-", "_")
        if not normalized.endswith("_env") and _is_sensitive_property(normalized):
            continue
        if isinstance(value, Mapping):
            safe[str(key)] = safe_catalog_properties(value)
        elif isinstance(value, list):
            safe[str(key)] = [safe_catalog_properties(item) if isinstance(item, Mapping) else item for item in value]
        else:
            safe[str(key)] = value
    return safe


def _is_sensitive_property(normalized: str) -> bool:
    if normalized in _SENSITIVE_PROPERTY_PARTS or normalized in {"auth", "credentials", "headers"}:
        return True
    return normalized.endswith(
        (
            "_api_key",
            "_access_token",
            "_auth_token",
            "_bearer_token",
            "_refresh_token",
            "_connection_string",
            "_credential",
            "_credentials",
            "_password",
            "_secret",
        )
    )


def public_catalog_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result.pop("_properties", None)
    return result


def property_matches(properties: Mapping[str, Any], path: str, expected: Any) -> bool:
    current: Any = properties
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    if isinstance(current, list):
        return expected in current
    return current == expected


def parse_property_filter(value: str) -> tuple[str, Any]:
    if "=" not in value:
        raise ValueError(f"model property filter must use FIELD=VALUE: {value}")
    path, raw = value.split("=", 1)
    path = path.strip()
    if not path or any(not part or not part.replace("_", "").replace("-", "").isalnum() for part in path.split(".")):
        raise ValueError(f"invalid model property path: {path!r}")
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if isinstance(parsed, (dict, list)):
        raise ValueError("model property filter values must be scalar")
    return path, parsed


def _property_values(value: Mapping[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(child, Mapping):
            yield from _property_values(child, path)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, (str, int, float, bool)) or item is None:
                    yield path, item
        elif isinstance(child, (str, int, float, bool)) or child is None:
            yield path, child


def _add_index(index: dict[str, list[int]], value: Any, position: int) -> None:
    if value is None:
        return
    index.setdefault(_index_key(value), []).append(position)


def _index_positions(indexes: Mapping[str, Any], name: str, value: Any) -> set[int]:
    index = indexes.get(name)
    if not isinstance(index, dict):
        return set()
    return set(index.get(_index_key(value), []))


def _index_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _update_file_digest(digest: Any, path: Path) -> None:
    digest.update(str(path.name).encode())
    if not path.is_file():
        digest.update(b"<missing>")
        return
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []
