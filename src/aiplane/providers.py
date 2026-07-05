from __future__ import annotations

import json
import os
import re
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from .config import dump_yaml, parse_yaml
from .model_catalog import ModelCatalog, ModelStatus, model_source
from .models import Profile
from .secrets import CredentialStore
from .runtime_catalog import PROVIDER_ENDPOINT_DEFAULTS


DEFAULT_PROVIDER_MODEL_LIMIT = 500
DEFAULT_MODEL_PROVIDERS_FILE = "model-providers.yaml"
USER_MODEL_PROVIDERS_FILE = "model-providers.user.yaml"
LEGACY_DEFAULT_SOURCE_PROVIDERS_FILE = "source-providers.yaml"
LEGACY_USER_SOURCE_PROVIDERS_FILE = "source-providers.user.yaml"

SUPPORTED_CATALOG_ADAPTERS = {
    "profile_catalog",
    "huggingface",
    "huggingface_gguf",
    "ollama",
    "civitai",
    "openai",
    "azure_openai",
    "elevenlabs",
}
SUPPORTED_ENDPOINT_FAMILIES = {
    "openai",
    "custom_openai_compatible",
    "anthropic",
    "azure_openai",
    "ollama_cloud",
    "azure_speech",
    "elevenlabs",
}


@dataclass(frozen=True)
class ProviderModelsResult:
    provider: str
    source: str
    models: list[str]
    reason: str
    model_metadata: dict[str, dict[str, Any]] | None = None


class ProviderRegistry:
    """Model provider registry.

    Provider means a model catalog that supplies model identifiers/artifacts.
    Runtimes such as vLLM, TGI, llama.cpp, and Transformers are handled by
    RuntimeCatalog, not here.
    """

    def __init__(self, profile: Profile):
        self.profile = profile
        self.catalog = ModelCatalog(profile)

    def list(
        self,
        orchestrators: list[str] | None = None,
        runtimes: list[str] | None = None,
        group_by: str | None = None,
        include_empty: bool = True,
        status: str = "all",
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if status not in {"enabled", "disabled", "all"}:
            raise ValueError("provider status must be enabled, disabled, or all")
        runtime_filter = {str(value) for value in runtimes or [] if value}
        rows = []
        catalog_by_provider: dict[str, list[dict[str, Any]]] = {}
        for row in self.catalog.list():
            catalog_by_provider.setdefault(str(row.get("provider") or ""), []).append(row)
        for name, source in self.model_providers(include_removed=True).items():
            removed = bool(source.get("removed"))
            enabled = bool(source.get("enabled", True)) and not removed
            if status == "enabled" and not enabled:
                continue
            if status == "disabled" and enabled:
                continue
            catalog_models = catalog_by_provider.get(name, [])
            if not catalog_models and not include_empty:
                continue
            row = {
                "name": name,
                "description": source.get("description"),
                "ownership": _provider_ownership(source),
                "typical_runtimes": source.get("typical_runtimes", []),
                "endpoint_family": source.get("endpoint_family"),
                "catalog_adapter": _provider_catalog_adapter(source),
                "auth": source.get("auth", {"required": False, "method": "none"}),
                "credential_ref": source.get("credential_ref"),
                "api_key_env": source.get("api_key_env"),
                "endpoint": source.get("endpoint"),
                "enabled": enabled,
                "removed": removed,
                "profile_models_count": len(catalog_models),
                "has_profile_catalog_entries": bool(catalog_models),
            }
            if runtime_filter and not runtime_filter.intersection(set(row["typical_runtimes"])):
                continue
            rows.append(row)
        rows = sorted(rows, key=lambda row: str(row["name"]))
        if group_by:
            return self._group(rows, group_by, runtime_filter)
        return rows

    def show(self, name: str) -> dict[str, Any]:
        providers = self.model_providers()
        if name not in providers or providers[name].get("removed"):
            raise ValueError(f"unknown catalog provider: {name}")
        catalog_models = [row for row in self.catalog.list() if row.get("provider") == name]
        provider = providers[name]
        return {
            "name": name,
            **provider,
            "ownership": _provider_ownership(provider),
            "profile_models_count": len(catalog_models),
            "profile_models": catalog_models,
        }

    def endpoint_families(self) -> dict[str, Any]:
        rows = []
        for name, provider in sorted(PROVIDER_ENDPOINT_DEFAULTS.items()):
            if provider.get("ownership") != "managed_service" or name not in SUPPORTED_ENDPOINT_FAMILIES:
                continue
            rows.append(
                {
                    "name": name,
                    "protocol": provider.get("protocol"),
                    "endpoint": provider.get("endpoint") or None,
                    "api_key_env": provider.get("api_key_env"),
                    "access_kind": (provider.get("access") or {}).get("kind"),
                    "notes": provider.get("notes"),
                }
            )
        rows.append(
            {
                "name": "custom_openai_compatible",
                "protocol": "openai_compatible",
                "endpoint": None,
                "api_key_env": None,
                "access_kind": "hosted_api",
                "notes": "Use for a provider or gateway that implements OpenAI-compatible /v1/models and inference routes.",
            }
        )
        adapter_notes = {
            "profile_catalog": "No live catalog API. Use manually curated profile/discovered entries.",
            "huggingface": "Hugging Face Hub model API, optionally scoped by author.",
            "huggingface_gguf": "Hugging Face Hub search filtered for GGUF-style artifacts.",
            "ollama": "Ollama model catalog adapter.",
            "civitai": "Civitai model catalog adapter.",
            "openai": "OpenAI-compatible /v1/models API; requires an endpoint and bearer/API key.",
            "azure_openai": "Azure OpenAI deployments API; requires endpoint and credentials.",
            "elevenlabs": "ElevenLabs voices API; requires credentials.",
        }
        return {
            "name": "provider_types",
            "endpoint_families": sorted(rows, key=lambda row: str(row["name"])),
            "catalog_adapters": [
                {"name": name, "requires_code": False, "notes": adapter_notes[name]}
                for name in sorted(SUPPORTED_CATALOG_ADAPTERS)
            ],
            "unsupported_provider_api_note": "If a provider does not match one of these endpoint families/catalog adapters, add code for a new adapter before enabling live discovery or tests.",
        }

    def set_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        providers = self.model_providers()
        if name not in providers:
            raise ValueError(f"unknown catalog provider: {name}")
        config = self._user_source_provider_config()
        row = config.setdefault(name, {})
        row["enabled"] = enabled
        row.pop("removed", None)
        path = self._write_user_source_provider_config(config)
        return {"name": name, "enabled": enabled, "path": str(path)}

    def set_all_enabled(self, enabled: bool) -> dict[str, Any]:
        config = self._user_source_provider_config()
        names = []
        for name in self.model_providers(include_removed=True):
            row = config.setdefault(name, {})
            row["enabled"] = enabled
            row.pop("removed", None)
            names.append(name)
        path = self._write_user_source_provider_config(config)
        return {
            "name": "all",
            "enabled": enabled,
            "providers": sorted(names),
            "path": str(path),
        }

    def add(
        self,
        name: str,
        description: str = "",
        typical_runtimes: list[str] | None = None,
        catalog_adapter: str | None = None,
        enabled: bool = True,
        ownership: str | None = None,
        endpoint_family: str | None = None,
        endpoint: str | None = None,
        credential_ref: str | None = None,
        api_key_env: str | None = None,
        auth_method: str = "none",
        requires_credentials: bool = False,
    ) -> dict[str, Any]:
        _validate_provider_name(name)
        runtimes = [str(value) for value in typical_runtimes or [] if value]
        resolved_ownership = ownership or ("managed_service" if endpoint_family else "self_managed")
        if resolved_ownership not in {"self_managed", "managed_service"}:
            raise ValueError("provider ownership must be self_managed or managed_service")
        if resolved_ownership == "managed_service" and runtimes:
            raise ValueError("managed-service providers use --endpoint-family, not --runtime")
        if resolved_ownership == "self_managed" and endpoint_family:
            raise ValueError("self-managed providers use --runtime, not --endpoint-family")
        if endpoint_family and endpoint_family not in SUPPORTED_ENDPOINT_FAMILIES:
            raise ValueError("unsupported endpoint family; run providers endpoint-types to see supported API families")
        resolved_catalog_adapter = catalog_adapter or "profile_catalog"
        if resolved_catalog_adapter not in SUPPORTED_CATALOG_ADAPTERS:
            raise ValueError(
                "unsupported catalog adapter; use one of: " + ", ".join(sorted(SUPPORTED_CATALOG_ADAPTERS))
            )
        if auth_method not in {"none", "api_key", "bearer", "oauth2", "custom"}:
            raise ValueError("provider auth method must be none, api_key, bearer, oauth2, or custom")
        if auth_method != "none":
            requires_credentials = True
        config = self._user_source_provider_config()
        row: dict[str, Any] = {
            "ownership": resolved_ownership,
            "description": description or f"User-defined model provider {name}",
            "typical_runtimes": runtimes,
            "catalog_adapter": resolved_catalog_adapter,
            "auth": {"required": bool(requires_credentials), "method": auth_method},
            "enabled": enabled,
        }
        if endpoint_family:
            row["endpoint_family"] = endpoint_family
        if endpoint:
            row["endpoint"] = endpoint
        if credential_ref:
            row["credential_ref"] = credential_ref
        if api_key_env:
            row["api_key_env"] = api_key_env
        config[name] = row
        path = self._write_user_source_provider_config(config)
        return {"name": name, **config[name], "path": str(path)}

    def remove(self, name: str) -> dict[str, Any]:
        providers = self.model_providers(include_removed=True)
        if name not in providers:
            raise ValueError(f"unknown catalog provider: {name}")
        config = self._user_source_provider_config()
        row = config.setdefault(name, {})
        row["enabled"] = False
        row["removed"] = True
        path = self._write_user_source_provider_config(config)
        return {"name": name, "removed": True, "path": str(path)}

    def init_defaults(self, overwrite: bool = False) -> dict[str, Any]:
        path = self.profile.root / DEFAULT_MODEL_PROVIDERS_FILE
        if path.exists() and not overwrite:
            raise ValueError(f"model provider defaults already exist: {path}")
        providers = self.default_model_providers()
        path.write_text(dump_yaml(providers), encoding="utf-8")
        return {
            "name": "model_provider_defaults",
            "path": str(path),
            "providers": sorted(providers),
        }

    def update_defaults(self) -> dict[str, Any]:
        path = self.profile.root / DEFAULT_MODEL_PROVIDERS_FILE
        existing = (
            _provider_mapping(parse_yaml(path.read_text(encoding="utf-8")), origin="default") if path.exists() else {}
        )
        providers = self.default_model_providers()
        preserved_enabled = []
        added = []
        updated = []
        for name, provider in providers.items():
            previous = existing.get(name, {})
            if "enabled" in previous:
                provider["enabled"] = bool(previous["enabled"])
                preserved_enabled.append(name)
            if name in existing:
                updated.append(name)
            else:
                added.append(name)
        path.write_text(dump_yaml(providers), encoding="utf-8")
        return {
            "name": "model_provider_defaults_update",
            "path": str(path),
            "providers": sorted(providers),
            "added": sorted(added),
            "updated": sorted(updated),
            "preserved_enabled": sorted(preserved_enabled),
            "notes": [
                "Provider properties were refreshed from built-in defaults.",
                "Existing enabled/disabled values in model-providers.yaml were preserved.",
                "User overrides in model-providers.user.yaml were not modified.",
            ],
        }

    def clear_config(self, scope: str) -> dict[str, Any]:
        if scope == "defaults":
            scope = "embedded"
        if scope not in {"embedded", "user", "all"}:
            raise ValueError("scope must be embedded, user, or all")
        removed = []
        defaults_path = self.profile.root / DEFAULT_MODEL_PROVIDERS_FILE
        user_path = self.profile.root / USER_MODEL_PROVIDERS_FILE
        legacy_defaults_path = self.profile.root / LEGACY_DEFAULT_SOURCE_PROVIDERS_FILE
        legacy_user_path = self.profile.root / LEGACY_USER_SOURCE_PROVIDERS_FILE
        paths = []
        if scope in {"embedded", "all"}:
            paths.extend([defaults_path, legacy_defaults_path])
        if scope in {"user", "all"}:
            paths.extend([user_path, legacy_user_path])
        for path in paths:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        if scope in {"embedded", "all"}:
            defaults_path.write_text("", encoding="utf-8")
            if str(defaults_path) not in removed:
                removed.append(str(defaults_path))
        return {
            "name": "model_provider_config_clear",
            "scope": scope,
            "suppresses_hardcoded_fallback": scope in {"embedded", "all"},
            "removed": removed,
        }

    def model_providers(self, include_removed: bool = False) -> dict[str, dict[str, Any]]:
        providers = self._default_source_provider_config()
        user = self._user_source_provider_config()
        for name, value in user.items():
            if not isinstance(value, dict):
                continue
            providers[name] = {**providers.get(name, {}), **value, "origin": "user"}
        if include_removed:
            return providers
        return {name: value for name, value in providers.items() if not value.get("removed")}

    def default_model_providers(self) -> dict[str, dict[str, Any]]:
        from .runtime_catalog import SOURCE_DEFINITIONS

        return {
            name: {
                **value,
                "enabled": bool(value.get("enabled", True)),
                "origin": "default",
            }
            for name, value in SOURCE_DEFINITIONS.items()
        }

    def _default_source_provider_config(self) -> dict[str, Any]:
        path = self.profile.root / DEFAULT_MODEL_PROVIDERS_FILE
        legacy_path = self.profile.root / LEGACY_DEFAULT_SOURCE_PROVIDERS_FILE
        user_path = self.profile.root / USER_MODEL_PROVIDERS_FILE
        legacy_user_path = self.profile.root / LEGACY_USER_SOURCE_PROVIDERS_FILE
        if path.exists():
            return _provider_mapping(parse_yaml(path.read_text(encoding="utf-8")), origin="default")
        if legacy_path.exists():
            return _provider_mapping(parse_yaml(legacy_path.read_text(encoding="utf-8")), origin="default")
        if not user_path.exists() and not legacy_user_path.exists():
            return self.default_model_providers()
        return {}

    def _user_source_provider_config(self) -> dict[str, Any]:
        path = self.profile.root / USER_MODEL_PROVIDERS_FILE
        legacy_path = self.profile.root / LEGACY_USER_SOURCE_PROVIDERS_FILE
        if path.exists():
            return _provider_mapping(
                parse_yaml(path.read_text(encoding="utf-8")),
                origin="user",
                keep_origin=False,
            )
        if legacy_path.exists():
            return _provider_mapping(
                parse_yaml(legacy_path.read_text(encoding="utf-8")),
                origin="user",
                keep_origin=False,
            )
        return {}

    def _write_user_source_provider_config(self, config: dict[str, Any]) -> Path:
        path = self.profile.root / USER_MODEL_PROVIDERS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_yaml(config), encoding="utf-8")
        return path

    def _group(
        self,
        rows: list[dict[str, Any]],
        group_by: str,
        key_filter: set[str] | None = None,
    ) -> dict[str, Any]:
        if group_by not in {"runtime", "ownership"}:
            raise ValueError("catalog providers can only be grouped by runtime or ownership")
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if group_by == "ownership":
                keys = [str(row.get("ownership") or "unknown")]
            else:
                keys = [str(value) for value in row.get("typical_runtimes") or ["none"]]
                if key_filter:
                    keys = [key for key in keys if key in key_filter]
            for key in keys:
                groups.setdefault(key, []).append(row)
        if group_by == "ownership":
            ordered_keys = [key for key in ["self_managed", "managed_service"] if key in groups]
            ordered_keys.extend(sorted(key for key in groups if key not in set(ordered_keys)))
        else:
            ordered_keys = sorted(groups)
        return {
            "name": "providers",
            "group_by": group_by,
            "groups": {key: sorted(groups[key], key=lambda item: str(item["name"])) for key in ordered_keys},
        }

    def doctor(self, name: str | None = None) -> list[ModelStatus]:
        if name is None:
            return self.catalog.doctor()
        providers = self.model_providers(include_removed=True)
        if name not in providers or providers[name].get("removed"):
            raise ValueError(f"unknown catalog provider: {name}")
        model_names = {alias for alias, model in self.catalog.models().items() if model_source(model) == name}
        return [status for status in self.catalog.doctor() if status.name in model_names]

    def test_connection(
        self, name: str, credential_ref: str | None = None, timeout: int | None = None
    ) -> dict[str, Any]:
        providers = self.model_providers(include_removed=True)
        provider_config = {
            **providers.get(name, {}),
            **self.catalog.providers().get(name, {}),
        }
        if name not in providers and not provider_config:
            raise ValueError(f"unknown provider: {name}")
        if providers.get(name, {}).get("removed"):
            raise ValueError(f"removed provider: {name}")

        credential_ref = credential_ref or str(provider_config.get("credential_ref") or "") or None
        credentials = CredentialStore()
        credential = credentials.resolve(credential_ref) if credential_ref else {}
        endpoint = str(credential.get("endpoint") or provider_config.get("endpoint") or "").rstrip("/")
        key_env = str(
            credential.get("api_key_env") or credential.get("token_env") or provider_config.get("api_key_env") or ""
        )
        api_key = (
            credentials.api_key(credential_ref) if credential_ref else (os.environ.get(key_env) if key_env else "")
        )
        timeout_seconds = int(timeout or provider_config.get("timeout_seconds") or 20)
        result = {
            "name": "provider_connection_test",
            "provider": name,
            "ok": False,
            "endpoint": endpoint or None,
            "credential_ref": credential_ref,
            "api_key_env": key_env or None,
            "has_api_key": bool(api_key),
        }
        if not api_key:
            result["reason"] = (
                f"missing credential {credential_ref}"
                if credential_ref
                else f"missing env var {key_env or 'provider api_key_env'}"
            )
            return result

        try:
            if name == "azure_openai":
                if not endpoint:
                    result["reason"] = "missing Azure OpenAI endpoint"
                    return result
                api_version = str(
                    provider_config.get("api_version")
                    or credential.get("api_version")
                    or os.environ.get("AZURE_OPENAI_API_VERSION")
                    or "2024-02-01"
                )
                base = endpoint[:-7] if endpoint.endswith("/openai") else endpoint
                url = f"{base}/openai/deployments?" + urlencode({"api-version": api_version})
                payload = _json_get(url, timeout=timeout_seconds, headers={"api-key": api_key})
                items = payload.get("data") if isinstance(payload, dict) else None
                if items is None and isinstance(payload, dict):
                    items = payload.get("value")
                result.update(
                    {
                        "ok": isinstance(items, list),
                        "method": "azure_openai_deployments",
                        "url": url,
                        "items_seen": len(items) if isinstance(items, list) else None,
                    }
                )
                if not result["ok"]:
                    result["reason"] = "unexpected Azure OpenAI deployments response"
                return result

            if name == "elevenlabs":
                endpoint = endpoint or "https://api.elevenlabs.io/v1"
                url = f"{endpoint}/voices"
                payload = _json_get(url, timeout=timeout_seconds, headers={"xi-api-key": api_key})
                voices = payload.get("voices") if isinstance(payload, dict) else None
                result.update(
                    {
                        "ok": isinstance(voices, list),
                        "endpoint": endpoint,
                        "method": "elevenlabs_voices",
                        "url": url,
                        "items_seen": len(voices) if isinstance(voices, list) else None,
                    }
                )
                if not result["ok"]:
                    result["reason"] = "unexpected ElevenLabs voices response"
                return result

            endpoint_family = str(provider_config.get("endpoint_family") or "")
            protocol = str(provider_config.get("protocol") or providers.get(name, {}).get("protocol") or "")
            if (
                name == "openai"
                or endpoint_family in {"openai", "custom_openai_compatible"}
                or "openai_compatible" in protocol
                or endpoint.endswith("/v1")
            ):
                endpoint = endpoint or "https://api.openai.com/v1"
                url = f"{endpoint}/models"
                payload = _json_get(
                    url,
                    timeout=timeout_seconds,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                items = payload.get("data") if isinstance(payload, dict) else None
                result.update(
                    {
                        "ok": isinstance(items, list),
                        "endpoint": endpoint,
                        "method": "openai_compatible_models",
                        "url": url,
                        "items_seen": len(items) if isinstance(items, list) else None,
                    }
                )
                if not result["ok"]:
                    result["reason"] = "unexpected OpenAI-compatible models response"
                return result

            result["reason"] = "no live provider connection test adapter is implemented for this provider yet"
            return result
        except Exception as exc:  # noqa: BLE001 - connection test should report failures as data.
            result["reason"] = str(exc)
            return result

    def models(
        self,
        name: str,
        query: str | None = None,
        limit: int = DEFAULT_PROVIDER_MODEL_LIMIT,
        online: bool = False,
    ) -> ProviderModelsResult:
        providers = self.model_providers()
        if name not in providers or providers[name].get("removed"):
            raise ValueError(f"unknown catalog provider: {name}")
        if providers[name].get("enabled") is False:
            return ProviderModelsResult(name, "disabled", [], "model provider is disabled")
        online_error = None
        if online:
            try:
                online_result = self._online_models(name, query=query, limit=limit)
            except Exception as exc:  # noqa: BLE001 - provider catalog adapters should degrade to the local catalog.
                online_result = None
                online_error = str(exc)
            if online_result is not None:
                return online_result
        models = sorted(
            str(model.get("model"))
            for model in self.catalog.models().values()
            if model_source(model) == name and model.get("model")
        )
        reason = "using aiplane profile catalog entries for this model provider"
        if online and online_error:
            if _provider_ownership(providers[name]) == "managed_service":
                return ProviderModelsResult(
                    name,
                    "error",
                    [],
                    f"online catalog query failed: {online_error}",
                )
            reason += f"; online catalog query failed: {online_error}"
        elif online:
            reason += "; no online catalog adapter is available for this model provider"
        if query:
            lowered = query.lower()
            models = [model for model in models if lowered in model.lower()]
            reason += f" filtered by query {query!r}"
        return ProviderModelsResult(name, "profile_catalog", models[:limit], reason)

    def _online_models(
        self,
        name: str,
        query: str | None = None,
        limit: int = DEFAULT_PROVIDER_MODEL_LIMIT,
    ) -> ProviderModelsResult | None:
        provider_config = self.model_providers().get(name, {})
        adapter = str(_provider_catalog_adapter(provider_config) or name)
        if adapter == "huggingface" or name == "huggingface":
            return self._huggingface_models(
                query=query,
                limit=limit,
                provider=name,
                author=provider_config.get("huggingface_author"),
            )
        if adapter == "huggingface_gguf" or name == "huggingface_gguf":
            return self._huggingface_models(
                query=query,
                limit=limit,
                gguf=True,
                provider=name,
                author=provider_config.get("huggingface_author"),
            )
        if adapter == "civitai" or name == "civitai":
            return self._civitai_models(query=query, limit=limit)
        if adapter == "ollama" or name == "ollama":
            return self._ollama_library_models(query=query, limit=limit)
        if adapter == "openai" or name == "openai":
            return self._openai_compatible_models(name, query=query, limit=limit)
        if adapter == "azure_openai" or name == "azure_openai":
            return self._azure_openai_deployments(query=query, limit=limit)
        if adapter == "elevenlabs" or name == "elevenlabs":
            return self._elevenlabs_voices(query=query, limit=limit)
        return None

    def _openai_compatible_models(
        self,
        name: str,
        query: str | None = None,
        limit: int = DEFAULT_PROVIDER_MODEL_LIMIT,
    ) -> ProviderModelsResult:
        provider_config = {
            **self.model_providers().get(name, {}),
            **self.catalog.providers().get(name, {}),
        }
        defaults = PROVIDER_ENDPOINT_DEFAULTS.get(name, {})
        endpoint = str(
            provider_config.get("endpoint")
            or defaults.get("endpoint")
            or ("https://api.openai.com/v1" if name == "openai" else "")
        ).rstrip("/")
        if not endpoint:
            raise ValueError(f"{name} discovery needs provider endpoint")
        credential_ref = str(provider_config.get("credential_ref") or "")
        key_env = str(provider_config.get("api_key_env") or defaults.get("api_key_env") or "")
        api_key = CredentialStore().api_key(credential_ref) if credential_ref else os.environ.get(key_env)
        if not api_key:
            need = f"credential {credential_ref}" if credential_ref else f"env var {key_env or 'provider api_key_env'}"
            raise ValueError(f"{name} discovery needs {need}")
        url = f"{endpoint}/models"
        payload = _json_get(
            url,
            timeout=int(provider_config.get("timeout_seconds") or defaults.get("timeout_seconds") or 20),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise RuntimeError(f"{name} returned an unexpected models response")
        ids: list[str] = []
        metadata: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            searchable = " ".join(
                str(value)
                for value in [
                    model_id,
                    item.get("owned_by"),
                    item.get("object"),
                ]
                if value
            )
            if query and query.lower() not in searchable.lower():
                continue
            ids.append(model_id)
            metadata[model_id] = {key: item[key] for key in ["id", "object", "created", "owned_by"] if key in item}
            if len(ids) >= max(1, int(limit)):
                break
        unique_ids = list(dict.fromkeys(ids))[: max(1, int(limit))]
        return ProviderModelsResult(
            name,
            "provider_api",
            unique_ids,
            f"queried OpenAI-compatible models API: {url}",
            {model_id: metadata.get(model_id, {}) for model_id in unique_ids},
        )

    def _azure_openai_deployments(
        self, query: str | None = None, limit: int = DEFAULT_PROVIDER_MODEL_LIMIT
    ) -> ProviderModelsResult:
        runtime_provider = self.catalog.providers().get("azure_openai", {})
        endpoint = str(runtime_provider.get("endpoint") or os.environ.get("AZURE_OPENAI_ENDPOINT") or "").rstrip("/")
        if not endpoint:
            raise ValueError("Azure OpenAI discovery needs provider endpoint or AZURE_OPENAI_ENDPOINT")
        api_version = str(
            runtime_provider.get("api_version") or os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-02-01"
        )
        credential_ref = str(runtime_provider.get("credential_ref") or "")
        key_env = str(runtime_provider.get("api_key_env") or "AZURE_OPENAI_API_KEY")
        api_key = CredentialStore().api_key(credential_ref) if credential_ref else os.environ.get(key_env)
        if not api_key:
            need = f"credential {credential_ref}" if credential_ref else f"env var {key_env}"
            raise ValueError(f"Azure OpenAI discovery needs {need}")
        base = endpoint[:-7] if endpoint.endswith("/openai") else endpoint
        url = f"{base}/openai/deployments?" + urlencode({"api-version": api_version})
        payload = _json_get(
            url,
            timeout=int(runtime_provider.get("timeout_seconds", 20)),
            headers={"api-key": api_key},
        )
        items = payload.get("data") if isinstance(payload, dict) else None
        if items is None and isinstance(payload, dict):
            items = payload.get("value")
        if not isinstance(items, list):
            raise RuntimeError("Azure OpenAI returned an unexpected deployments response")
        ids: list[str] = []
        metadata: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            deployment_id = item.get("id") or item.get("name")
            if not deployment_id:
                continue
            model_id = str(deployment_id)
            if query and query.lower() not in model_id.lower():
                properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                model_info = item.get("model") or properties.get("model")
                if query.lower() not in str(model_info or "").lower():
                    continue
            ids.append(model_id)
            metadata[model_id] = {
                key: item[key] for key in ["id", "name", "model", "created_at", "updated_at", "status"] if key in item
            }
            if isinstance(item.get("properties"), dict):
                metadata[model_id]["properties"] = item["properties"]
            if len(ids) >= max(1, int(limit)):
                break
        unique_ids = sorted(dict.fromkeys(ids))[: max(1, int(limit))]
        return ProviderModelsResult(
            "azure_openai",
            "provider_api",
            unique_ids,
            f"queried Azure OpenAI deployments API: {url}",
            {model_id: metadata.get(model_id, {}) for model_id in unique_ids},
        )

    def _elevenlabs_voices(
        self, query: str | None = None, limit: int = DEFAULT_PROVIDER_MODEL_LIMIT
    ) -> ProviderModelsResult:
        runtime_provider = self.catalog.providers().get("elevenlabs", {})
        endpoint = str(
            runtime_provider.get("endpoint") or os.environ.get("ELEVENLABS_ENDPOINT") or "https://api.elevenlabs.io/v1"
        ).rstrip("/")
        credential_ref = str(runtime_provider.get("credential_ref") or "")
        key_env = str(runtime_provider.get("api_key_env") or "ELEVENLABS_API_KEY")
        api_key = CredentialStore().api_key(credential_ref) if credential_ref else os.environ.get(key_env)
        if not api_key:
            need = f"credential {credential_ref}" if credential_ref else f"env var {key_env}"
            raise ValueError(f"ElevenLabs voice discovery needs {need}")
        url = f"{endpoint}/voices"
        payload = _json_get(
            url,
            timeout=int(runtime_provider.get("timeout_seconds", 20)),
            headers={"xi-api-key": api_key},
        )
        items = payload.get("voices") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("ElevenLabs returned an unexpected voices response")
        ids: list[str] = []
        metadata: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            voice_id = str(item.get("voice_id") or item.get("voiceId") or item.get("id") or "").strip()
            name = str(item.get("name") or voice_id).strip()
            if not voice_id:
                continue
            searchable = " ".join(
                str(value)
                for value in [
                    voice_id,
                    name,
                    item.get("category"),
                    item.get("description"),
                ]
                if value
            )
            if query and query.lower() not in searchable.lower():
                continue
            ids.append(voice_id)
            metadata[voice_id] = {
                "voice_id": voice_id,
                "name": name,
                "provider": "elevenlabs",
                "pipeline_tag": "text-to-speech",
                "category": item.get("category"),
                "description": item.get("description"),
                "labels": (item.get("labels") if isinstance(item.get("labels"), dict) else {}),
            }
            if len(ids) >= max(1, int(limit)):
                break
        unique_ids = list(dict.fromkeys(ids))[: max(1, int(limit))]
        return ProviderModelsResult(
            "elevenlabs",
            "provider_api",
            unique_ids,
            f"queried ElevenLabs voices API: {url}",
            {voice_id: metadata.get(voice_id, {}) for voice_id in unique_ids},
        )

    def _huggingface_models(
        self,
        query: str | None = None,
        limit: int = DEFAULT_PROVIDER_MODEL_LIMIT,
        gguf: bool = False,
        provider: str | None = None,
        author: object | None = None,
    ) -> ProviderModelsResult:
        params: dict[str, str | int] = {
            "limit": max(1, min(int(limit), DEFAULT_PROVIDER_MODEL_LIMIT)),
            "sort": "downloads",
            "direction": -1,
        }
        if query:
            params["search"] = query
        if author:
            params["author"] = str(author)
        if gguf:
            search = str(params.get("search") or "")
            if "gguf" not in search.lower():
                search = (search + " GGUF").strip()
            params["search"] = search or "GGUF"
        url = "https://huggingface.co/api/models?" + urlencode(params)
        payload = _json_get(url, timeout=20)
        if not isinstance(payload, list):
            raise RuntimeError("Hugging Face returned an unexpected model catalog response")
        ids = []
        metadata = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            model_id = item.get("modelId") or item.get("id")
            if model_id:
                model_key = str(model_id)
                ids.append(model_key)
                metadata[model_key] = {
                    key: item[key]
                    for key in [
                        "author",
                        "downloads",
                        "likes",
                        "pipeline_tag",
                        "tags",
                        "lastModified",
                    ]
                    if key in item
                }
        result_provider = provider or ("huggingface_gguf" if gguf else "huggingface")
        unique_ids = sorted(dict.fromkeys(ids))
        return ProviderModelsResult(
            result_provider,
            "source_api",
            unique_ids,
            f"queried Hugging Face Hub API: {url}",
            {model_id: metadata.get(model_id, {}) for model_id in unique_ids},
        )

    def _civitai_models(
        self, query: str | None = None, limit: int = DEFAULT_PROVIDER_MODEL_LIMIT
    ) -> ProviderModelsResult:
        target = max(1, min(int(limit), DEFAULT_PROVIDER_MODEL_LIMIT))
        ids = []
        metadata_by_id = {}
        urls = []
        page = 1
        while len(ids) < target:
            page_limit = min(100, target - len(ids))
            params: dict[str, str | int] = {"limit": page_limit, "page": page}
            if query:
                params["query"] = query
            url = "https://civitai.com/api/v1/models?" + urlencode(params)
            urls.append(url)
            payload = _json_get(url, timeout=20)
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise RuntimeError("Civitai returned an unexpected model catalog response")
            items = payload.get("items", [])
            if not items:
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("id")
                name = str(item.get("name") or "model").lower()
                slug = "".join(ch if ch.isalnum() else "-" for ch in name).strip("-")
                if model_id:
                    source_id = f"civitai:{model_id}:{slug}" if slug else f"civitai:{model_id}"
                    ids.append(source_id)
                    metadata_by_id[source_id] = {
                        key: item[key] for key in ["id", "name", "type", "nsfw", "stats", "tags"] if key in item
                    }
                if len(ids) >= target:
                    break
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            if not metadata.get("nextPage"):
                break
            page += 1
        unique_ids = sorted(dict.fromkeys(ids))[:target]
        return ProviderModelsResult(
            "civitai",
            "source_api",
            unique_ids,
            f"queried Civitai models API: {urls[0]}" + (f" and {len(urls) - 1} more page(s)" if len(urls) > 1 else ""),
            {model_id: metadata_by_id.get(model_id, {}) for model_id in unique_ids},
        )

    def _ollama_library_models(
        self, query: str | None = None, limit: int = DEFAULT_PROVIDER_MODEL_LIMIT
    ) -> ProviderModelsResult:
        params = {}
        if query:
            params["q"] = query
        url = "https://ollama.com/library" + (("?" + urlencode(params)) if params else "")
        html = _text_get(url, timeout=20)
        ids = []
        metadata: dict[str, dict[str, Any]] = {}
        for match in re.finditer(r'href="/library/([a-zA-Z0-9_.-]+)"[^>]*>\s*([^<]+)', html):
            model_id = unescape(match.group(1)).strip()
            label = unescape(match.group(2)).strip()
            if not model_id or model_id in ids:
                continue
            if query and query.lower() not in model_id.lower() and query.lower() not in label.lower():
                continue
            ids.append(model_id)
            metadata[model_id] = {"name": label}
            if len(ids) >= max(1, int(limit)):
                break
        if not ids:
            for match in re.finditer(r"/library/([a-zA-Z0-9_.-]+)", html):
                model_id = unescape(match.group(1)).strip()
                if model_id and model_id not in ids:
                    ids.append(model_id)
                if len(ids) >= max(1, int(limit)):
                    break
        return ProviderModelsResult(
            "ollama",
            "source_api",
            ids[: max(1, int(limit))],
            f"scraped Ollama Library page: {url}",
            {model_id: metadata.get(model_id, {}) for model_id in ids[: max(1, int(limit))]},
        )


def _json_get(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    return json.loads(_text_get(url, timeout=timeout, accept="application/json", headers=headers))


def _text_get(
    url: str,
    timeout: int = 20,
    accept: str = "text/html,application/json,text/plain",
    headers: dict[str, str] | None = None,
) -> str:
    request_headers = {"Accept": accept, "User-Agent": "aiplane/0.1", **(headers or {})}
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _provider_ownership(provider: dict[str, Any]) -> str:
    if provider.get("ownership"):
        return str(provider.get("ownership"))
    if provider.get("endpoint_family"):
        return "managed_service"
    runtimes = {str(value) for value in provider.get("typical_runtimes", []) if value}
    managed = {
        "openai",
        "anthropic",
        "azure_openai",
        "ollama_cloud",
        "azure_speech",
        "elevenlabs",
    }
    return "managed_service" if runtimes and runtimes.issubset(managed) else "self_managed"


def _provider_catalog_adapter(provider: dict[str, Any]) -> str | None:
    value = provider.get("catalog_adapter") or provider.get("online_adapter")
    return str(value) if value else None


def _provider_mapping(data: dict[str, Any], origin: str, keep_origin: bool = True) -> dict[str, Any]:
    if isinstance(data.get("providers"), dict):
        data = data["providers"]
    result = {}
    for name, value in data.items():
        if isinstance(value, dict):
            row = dict(value)
            if "catalog_adapter" not in row and "online_adapter" in row:
                row["catalog_adapter"] = row.pop("online_adapter")
            if keep_origin:
                row.setdefault("origin", origin)
            result[str(name)] = row
    return result


def _validate_provider_name(name: str) -> None:
    if not name or not re.match(r"^[a-zA-Z0-9_.-]+$", name):
        raise ValueError("provider name must contain only letters, digits, dot, underscore, or dash")
