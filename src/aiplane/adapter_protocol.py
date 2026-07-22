"""Small, dependency-free contract for catalog adapter contributors."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Protocol, runtime_checkable

ADAPTER_CONTRACT_VERSION = "1.0"
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_FORBIDDEN = {"api_key", "token", "password", "secret", "authorization"}


@dataclass(frozen=True)
class AdapterRequest:
    provider: str
    query: str | None = None
    limit: int = 100


@dataclass(frozen=True)
class AdapterModel:
    id: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterResult:
    contract_version: str
    adapter: str
    source_contacted: bool
    models: tuple[AdapterModel, ...]
    provenance: dict[str, str]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["models"] = [asdict(model) for model in self.models]
        payload["warnings"] = list(self.warnings)
        return payload


@runtime_checkable
class CatalogAdapter(Protocol):
    name: str

    def discover(self, request: AdapterRequest) -> AdapterResult: ...


def validate_result(payload: dict[str, Any]) -> AdapterResult:
    if payload.get("contract_version") != ADAPTER_CONTRACT_VERSION:
        raise ValueError(f"adapter contract_version must be {ADAPTER_CONTRACT_VERSION}")
    adapter = str(payload.get("adapter") or "")
    if not _NAME.fullmatch(adapter):
        raise ValueError("adapter must be a stable snake_case name")
    _reject_secrets(payload)
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source"):
        raise ValueError("adapter result provenance.source is required")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise ValueError("adapter result models must be a list")
    models: list[AdapterModel] = []
    seen: set[str] = set()
    for item in raw_models:
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError("every adapter model requires a non-empty id")
        model_id = str(item["id"]).strip()
        if model_id in seen:
            raise ValueError(f"duplicate adapter model id: {model_id}")
        seen.add(model_id)
        provider = str(item.get("provider") or "").strip()
        if not provider:
            raise ValueError(f"adapter model {model_id!r} requires provider")
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError(f"adapter model {model_id!r} metadata must be an object")
        models.append(AdapterModel(model_id, provider, metadata))
    warnings = payload.get("warnings") or []
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise ValueError("adapter result warnings must be a string list")
    return AdapterResult(
        contract_version=ADAPTER_CONTRACT_VERSION,
        adapter=adapter,
        source_contacted=bool(payload.get("source_contacted")),
        models=tuple(models),
        provenance={str(key): str(value) for key, value in provenance.items()},
        warnings=tuple(warnings),
    )


def validate_result_file(path: Path) -> AdapterResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("adapter result must be a JSON object")
    return validate_result(payload)


def run_adapter(adapter: CatalogAdapter, request: AdapterRequest) -> AdapterResult:
    if not isinstance(adapter, CatalogAdapter):
        raise ValueError("adapter does not implement the catalog adapter protocol")
    result = adapter.discover(request)
    return validate_result(result.to_dict())


def _reject_secrets(value: Any, path: str = "result") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower().replace("-", "_")
            if lowered in _FORBIDDEN or lowered.endswith(("_api_key", "_token", "_password", "_secret")):
                raise ValueError(f"secret-bearing field is forbidden in adapter results: {path}.{key}")
            _reject_secrets(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secrets(child, f"{path}[{index}]")
