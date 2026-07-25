"""Validated, read-only fallback model catalogs for offline planning."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import parse_yaml
from .secrets import contains_secret

CONTRACT_VERSION = "1.0"
_RECORD_TYPE = "offline_model_catalog"
_SENSITIVE_KEY_MARKERS = {
    "apikey",
    "accesstoken",
    "authorization",
    "bearertoken",
    "clientsecret",
    "connectionstring",
    "credential",
    "credentials",
    "password",
    "privatekey",
    "refreshtoken",
    "sastoken",
    "secret",
    "subscriptionkey",
    "token",
}


def load_offline_catalog(path: Path) -> dict[str, Any]:
    """Load a reviewed fallback catalog without persisting it to a profile."""
    text = path.read_text(encoding="utf-8")
    payload = _parse_catalog(text)
    if not isinstance(payload, dict):
        raise ValueError("offline catalog must contain a mapping")
    if payload.get("contract_version") != CONTRACT_VERSION or payload.get("record_type") != _RECORD_TYPE:
        raise ValueError("offline catalog has an unsupported contract")
    models = payload.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("offline catalog must contain a non-empty models mapping")

    normalized: dict[str, dict[str, Any]] = {}
    for alias, raw in sorted(models.items()):
        name = str(alias).strip()
        if not name or not isinstance(raw, dict):
            raise ValueError("offline catalog model aliases must map to objects")
        provider = str(raw.get("provider") or "").strip()
        native_id = str(raw.get("model") or "").strip()
        if not provider or not native_id:
            raise ValueError(f"offline catalog model {name!r} requires provider and model")
        if _contains_secret_material(raw):
            raise ValueError(f"offline catalog model {name!r} contains secret-like material")
        normalized[name] = {**raw, "provider": provider, "model": native_id, "origin": "offline_catalog"}

    return {
        "models": normalized,
        "metadata": {"contract_version": CONTRACT_VERSION, "record_type": _RECORD_TYPE, "source": str(path)},
    }


def _parse_catalog(text: str) -> Any:
    stripped = text.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("offline catalog contains invalid JSON") from exc
    return parse_yaml(text)


def _contains_secret_material(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_is_sensitive_key(str(key)) or _contains_secret_material(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_material(item) for item in value)
    return contains_secret(value)


def _is_sensitive_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    return normalized in _SENSITIVE_KEY_MARKERS or any(
        normalized.endswith(marker) for marker in _SENSITIVE_KEY_MARKERS if len(marker) >= 6
    )
