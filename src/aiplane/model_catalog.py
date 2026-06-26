from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .backends import BackendResult, OllamaBackend, OpenAICompatibleBackend
from .models import Profile


GENERATED_MODELS_FILE = "models.generated.yaml"


@dataclass(frozen=True)
class ModelStatus:
    name: str
    provider: str
    configured: bool
    usable: bool
    reason: str


class ModelCatalog:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.config = profile.models or {}
        self.generated_config = self._load_generated_config()

    def providers(self) -> dict[str, dict[str, Any]]:
        return _dict_of_dicts(self.config.get("providers", {}))

    def models(self) -> dict[str, dict[str, Any]]:
        generated = _dict_of_dicts(self.generated_config.get("models", {}))
        curated = _dict_of_dicts(self.config.get("models", {}))
        return {**generated, **curated}

    def defaults(self) -> dict[str, Any]:
        defaults = self.config.get("defaults", {})
        return defaults if isinstance(defaults, dict) else {}

    def default_model(self, role: str, require_enabled: bool = True) -> dict[str, Any] | None:
        name = self.defaults().get(role)
        models = self.models()
        if not name or str(name) not in models:
            return None
        model = models[str(name)]
        if require_enabled and not bool(model.get("enabled", True)):
            return None
        return {"role": role, "name": str(name), "model": model}

    def default_summary(self) -> dict[str, Any]:
        rows = []
        models = self.models()
        for role, name in self.defaults().items():
            model = models.get(str(name))
            rows.append({
                "role": role,
                "name": name,
                "exists": isinstance(model, dict),
                "enabled": bool(model.get("enabled", True)) if isinstance(model, dict) else False,
                "provider": model.get("provider") if isinstance(model, dict) else None,
                "model": model.get("model") if isinstance(model, dict) else None,
            })
        return {"defaults": rows}

    def set_default(self, role: str, name: str) -> dict[str, Any]:
        if not role or "/" in role or "\\" in role:
            raise ValueError("default role must be a simple name")
        model = self.get(name)
        self.config.setdefault("defaults", {})[role] = name
        path = self.profile.root / "models.yaml"
        from .config import dump_yaml

        path.write_text(dump_yaml(self.config), encoding="utf-8")
        return {"role": role, "name": name, "provider": model.get("provider"), "model": model.get("model"), "path": str(path)}

    def list(self) -> list[dict[str, Any]]:
        rows = []
        from .runtime_catalog import RuntimeCatalog
        runtime_catalog = RuntimeCatalog(self.profile)
        from .benchmarks import latest_benchmark_summary

        for name, model in self.models().items():
            serving_provider = str(model.get("provider") or "")
            provider = self.providers().get(serving_provider, {})
            source_provider = model_source(model)
            capabilities = capability_profile(model)

            latest_benchmark = latest_benchmark_summary(self.profile, name)
            supported_runtimes = runtime_catalog.compatible_runtimes_for_entry(model, include_gui=True)
            runtime_endpoint = serving_provider
            configured_runtime_endpoints = [runtime for runtime in supported_runtimes if runtime in self.providers()]
            rows.append({
                "name": name,
                "provider": source_provider,
                "source": source_provider,
                "model": model.get("model"),
                "capability_avg_score": _capability_average(capabilities),
                "latest_benchmark": latest_benchmark,
                "ownership": ownership_for_model(model, provider),
                "runtime": model.get("preferred_runtime") or provider.get("runtime") or runtime_endpoint,
                "supported_runtimes": supported_runtimes,
                "runtime_endpoint": runtime_endpoint,
                "configured_runtime_endpoints": configured_runtime_endpoints,
                "roles": model.get("roles", []),
                "enabled": bool(model.get("enabled", True)),
                "capability_tags": capability_tags(capabilities),
                "top_capabilities": top_capabilities(capabilities),
                "capabilities": capabilities,
            })
        return sorted(rows, key=lambda row: row["name"])

    def filter(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.list()
        capability_filters = filters.get("capabilities") or {}
        result = []
        from .runtime_catalog import RuntimeCatalog

        runtime_catalog = RuntimeCatalog(self.profile)
        for row in rows:
            model = self.get(str(row["name"]))
            if filters.get("provider") and row.get("provider") != filters["provider"]:
                continue
            if filters.get("source") and row.get("source") != filters["source"]:
                continue
            if filters.get("runtime") and filters["runtime"] not in runtime_catalog.supported_runtimes(str(row["name"])):
                continue
            roles_filter = _string_list(filters.get("roles") or filters.get("role"))
            if roles_filter and not any(role in row.get("roles", []) for role in roles_filter):
                continue
            if filters.get("enabled_only") and not row.get("enabled"):
                continue
            if filters.get("ownership") and row.get("ownership") != filters["ownership"]:
                continue
            score_source = filters.get("score_source")
            if score_source and row.get("capabilities", {}).get("score_source") != score_source:
                continue
            min_capability_avg = filters.get("min_capability_avg_score")
            if min_capability_avg is not None and float(row.get("capability_avg_score", 0)) < float(min_capability_avg):
                continue
            benchmark = row.get("latest_benchmark") if isinstance(row.get("latest_benchmark"), dict) else None
            min_benchmark = filters.get("min_benchmark_score")
            if min_benchmark is not None:
                if not benchmark or float(benchmark.get("average_score", 0)) < float(min_benchmark):
                    continue
            if filters.get("require_benchmark") and not benchmark:
                continue
            scores = row["capabilities"]["scores"]
            if any(int(scores.get(name, 0)) < minimum for name, minimum in capability_filters.items()):
                continue
            min_ram = filters.get("max_min_ram_gb")
            if min_ram is not None and _number_or_none(model.get("min_ram_gb")) and _number_or_none(model.get("min_ram_gb")) > float(min_ram):
                continue
            min_vram = filters.get("max_min_vram_gb")
            if min_vram is not None and _number_or_none(model.get("min_vram_gb")) and _number_or_none(model.get("min_vram_gb")) > float(min_vram):
                continue
            result.append(row)
        return sorted(result, key=lambda row: str(row["name"]))

    def sort_rows(self, rows: list[dict[str, Any]], sort_by: str = "name", roles: list[str] | None = None) -> list[dict[str, Any]]:
        roles = _string_list(roles)
        sort_by = sort_by or "name"
        ranked_rows = [_recommendation_row(row, roles) for row in rows] if roles or sort_by == "role" else [dict(row) for row in rows]
        if sort_by == "name":
            return sorted(ranked_rows, key=lambda row: str(row.get("name", "")))
        if sort_by == "avg":
            return sorted(ranked_rows, key=lambda row: (-float(row.get("capability_avg_score", 0)), str(row.get("name", ""))))
        if sort_by == "benchmark":
            return sorted(ranked_rows, key=lambda row: (-_benchmark_score(row), -float(row.get("capability_avg_score", 0)), str(row.get("name", ""))))
        if sort_by == "role":
            if roles:
                return sorted(ranked_rows, key=lambda row: (-float(row.get("role_score", 0)), -float(row.get("capability_avg_score", 0)), str(row.get("name", ""))))
            return sorted(ranked_rows, key=lambda row: (-float(row.get("capability_avg_score", 0)), str(row.get("name", ""))))
        raise ValueError(f"unknown model sort: {sort_by}")

    def set_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        curated = _dict_of_dicts(self.config.get("models", {}))
        generated = _dict_of_dicts(self.generated_config.get("models", {}))
        if name in curated:
            curated[name]["enabled"] = bool(enabled)
            self.config["models"] = curated
            from .config import dump_yaml

            path = self.profile.root / "models.yaml"
            path.write_text(dump_yaml(self.config), encoding="utf-8")
            return {"name": name, "enabled": bool(enabled), "path": str(path)}
        if name in generated:
            generated[name]["enabled"] = bool(enabled)
            self.generated_config["models"] = generated
            path = self._write_generated_config()
            return {"name": name, "enabled": bool(enabled), "path": str(path)}
        raise ValueError(f"unknown model: {name}")

    def refresh(self, provider_name: str = "ollama", write: bool = False, enable: bool = True, online: bool = True, query: str | None = None, limit: int = 500, progress: Callable[[str, str, str], None] | None = None, verbose: bool = False) -> dict[str, Any]:
        from .config import dump_yaml
        from .providers import ProviderRegistry
        from .runtime_catalog import RuntimeCatalog

        if progress:
            progress("connecting", provider_name, "")
        try:
            discovered = ProviderRegistry(self.profile).models(provider_name, query=query, limit=limit, online=online)
        except Exception as exc:
            if progress:
                progress("failed", provider_name, str(exc))
            raise
        if progress:
            progress("succeeded", provider_name, f"{len(discovered.models)} source model(s)")
        runtime_catalog = RuntimeCatalog(self.profile)
        all_models = self.models()
        curated_models = _dict_of_dicts(self.config.get("models", {}))
        generated_models = _dict_of_dicts(self.generated_config.get("models", {}))
        provider_models = [model for model in all_models.values() if model_source(model) == provider_name]
        provider_imported_models = [model for model in provider_models if _is_refresh_imported_model(model)]
        provider_curated_models = [model for model in provider_models if not _is_refresh_imported_model(model)]
        existing_by_id = {str(model.get("model")): name for name, model in all_models.items() if model_source(model) == provider_name and model.get("model")}
        existing = set(existing_by_id)
        changed_rows = []
        matched_count = 0
        new_count = 0
        update_count = 0
        source_api_contacted = discovered.source in {"provider_api", "source_api"}
        metadata_by_model = discovered.model_metadata or {}
        curated_dirty = False
        generated_dirty = False
        for model_id in discovered.models:
            source_metadata = metadata_by_model.get(str(model_id), {})
            if model_id in existing:
                matched_count += 1
                name = existing_by_id[model_id]
                model = all_models.get(name, {})
                if source_api_contacted and isinstance(model, dict):
                    merged = _merge_source_discovered_model(model, provider_name, str(model_id), source_metadata)
                    if merged != model:
                        status = "updated" if write else "would_update"
                        changed_rows.append(_refresh_model_row(name, merged, runtime_catalog, refresh_status=status, provider_visible=True, provider_reason=discovered.reason))
                        update_count += 1
                        if write:
                            if name in curated_models and not _is_refresh_imported_model(curated_models[name]):
                                curated_models[name] = merged
                                curated_dirty = True
                            else:
                                if name in curated_models:
                                    curated_models.pop(name, None)
                                    curated_dirty = True
                                generated_models[name] = merged
                                generated_dirty = True
                continue
            name = _unique_model_alias(all_models, provider_name, model_id)
            entry = _discovered_model_entry(provider_name, model_id, enable=enable, source_metadata=source_metadata)
            status = "imported" if write else "would_import"
            changed_rows.append(_refresh_model_row(name, entry, runtime_catalog, refresh_status=status, provider_visible=True, provider_reason=discovered.reason))
            new_count += 1
            if write:
                generated_models[name] = entry
                all_models[name] = entry
                generated_dirty = True
                existing.add(model_id)
                existing_by_id[model_id] = name

        prune_enabled = source_api_contacted and query is None and (discovered.source == "provider_api" or len(discovered.models) < int(limit))
        remove_count = 0
        discovered_ids = {str(model_id) for model_id in discovered.models}
        if prune_enabled:
            for name, model in list(all_models.items()):
                if model_source(model) != provider_name:
                    continue
                if not _is_refresh_imported_model(model):
                    continue
                model_id = str(model.get("model") or "")
                if model_id in discovered_ids:
                    continue
                status = "removed" if write else "would_remove"
                changed_rows.append(_refresh_model_row(name, model, runtime_catalog, refresh_status=status, provider_visible=False, provider_reason=discovered.reason))
                remove_count += 1
                if write:
                    if name in generated_models:
                        generated_models.pop(name, None)
                        generated_dirty = True
                    elif name in curated_models:
                        curated_models.pop(name, None)
                        curated_dirty = True
                    all_models.pop(name, None)

        path = self.profile.root / "models.yaml"
        generated_path = self._generated_path()
        if write and (curated_dirty or generated_dirty):
            self.config["models"] = curated_models
            self.generated_config["models"] = generated_models
            if curated_dirty:
                path.write_text(dump_yaml(self.config), encoding="utf-8")
            if generated_dirty:
                self._write_generated_config()

        changed_rows = sorted(changed_rows, key=lambda row: (str(row.get("runtime_endpoint")), str(row.get("refresh_status")), str(row.get("name"))))
        changes = {
            "imported": new_count if write else 0,
            "would_import": new_count if not write else 0,
            "updated": update_count if write else 0,
            "would_update": update_count if not write else 0,
            "removed": remove_count if write else 0,
            "would_remove": remove_count if not write else 0,
        }
        provider_config = self.providers().get(provider_name, {})
        provider_result = {
            "ownership": str(provider_config.get("ownership") or ("managed_service" if provider_name in {"openai", "anthropic", "azure_openai", "ollama_cloud"} else "self_managed")),
            "status": _refresh_status(changes),
            "source_contacted": source_api_contacted,
            "prune_enabled": prune_enabled,
            "source_discovery_method": discovered.source,
            "source_discovery_reason": discovered.reason,
            "source_models_returned": len(discovered.models),
            "profile_models_before_refresh": len(provider_models),
            "profile_curated_models_before_refresh": len(provider_curated_models),
            "profile_refresh_imported_models_before_refresh": len(provider_imported_models),
            "source_models_already_profiled": matched_count,
            "source_models_to_import": new_count,
            "source_models_to_update": update_count,
            "model_changes_count": len(changed_rows),
            "changes": changes,
        }
        if verbose:
            provider_result["model_changes"] = changed_rows
        return {
            "name": "model_catalog_refresh",
            "write": write,
            "new_entries_enabled": enable,
            "online": online,
            "query": query,
            "limit": limit,
            "verbose": verbose,
            "path": str(path),
            "generated_path": str(generated_path),
            "changes": changes,
            "results": {provider_name: provider_result},
        }


    def refresh_all(self, write: bool = True, enable: bool = True, include_empty_providers: bool = False, online: bool = True, query: str | None = None, limit: int = 500, provider_limits: dict[str, int] | None = None, progress: Callable[[str, str, str], None] | None = None, verbose: bool = False) -> dict[str, Any]:
        from .providers import ProviderRegistry
        provider_rows = ProviderRegistry(self.profile).list(include_empty=True)
        results: dict[str, Any] = {}
        skipped_providers = []
        for provider_row in provider_rows:
            provider_name = str(provider_row["name"])
            if provider_name == "local_file":
                continue
            if provider_row.get("enabled") is False:
                skipped_providers.append({
                    "name": provider_name,
                    "reason": "model provider is disabled",
                    "typical_runtimes": provider_row.get("typical_runtimes", []),
                    "source_contacted": False,
                })
                continue
            try:
                provider_limit = int((provider_limits or {}).get(provider_name, limit))
                result = self.refresh(provider_name, write=write, enable=enable, online=online, query=query, limit=provider_limit, progress=progress, verbose=verbose)
                provider_result = result.get("results", {}).get(provider_name, {})
                results[provider_name] = provider_result
            except Exception as exc:  # noqa: BLE001 - all-provider refresh should report provider-specific failures.
                results[provider_name] = {
                    "ownership": "self_managed",
                    "status": "failed",
                    "write": write,
                    "new_entries_enabled": enable,
                    "source_contacted": False,
                    "prune_enabled": False,
                    "source_discovery_method": "error",
                    "source_discovery_reason": str(exc),
                    "source_models_returned": 0,
                    "profile_models_before_refresh": len([model for model in self.models().values() if model_source(model) == provider_name]),
                    "profile_curated_models_before_refresh": len([model for model in self.models().values() if model_source(model) == provider_name and not _is_refresh_imported_model(model)]),
                    "profile_refresh_imported_models_before_refresh": len([model for model in self.models().values() if model_source(model) == provider_name and _is_refresh_imported_model(model)]),
                    "source_models_already_profiled": 0,
                    "source_models_to_import": 0,
                    "source_models_to_update": 0,
                    "changes": {"imported": 0, "would_import": 0, "updated": 0, "would_update": 0, "removed": 0, "would_remove": 0},
                    "model_changes_count": 0,
                    "error": str(exc),
                }
        rows = list(results.values())
        return {
            "name": "model_catalog_refresh_all",
            "write": write,
            "new_entries_enabled": enable,
            "online": online,
            "query": query,
            "limit": limit,
            "verbose": verbose,
            "provider_limits": provider_limits or {},
            "providers_total": len(rows),
            "providers_updated": sum(1 for row in rows if row.get("status") == "updated"),
            "providers_would_update": sum(1 for row in rows if row.get("status") == "would_update"),
            "providers_failed": sum(1 for row in rows if row.get("status") == "failed"),
            "providers_skipped_empty": len(skipped_providers),
            "changes": {
                "imported": sum(int(row.get("changes", {}).get("imported", 0)) for row in rows),
                "would_import": sum(int(row.get("changes", {}).get("would_import", 0)) for row in rows),
                "updated": sum(int(row.get("changes", {}).get("updated", 0)) for row in rows),
                "would_update": sum(int(row.get("changes", {}).get("would_update", 0)) for row in rows),
                "removed": sum(int(row.get("changes", {}).get("removed", 0)) for row in rows),
                "would_remove": sum(int(row.get("changes", {}).get("would_remove", 0)) for row in rows),
            },
            "results": results,
            "skipped_providers": skipped_providers,
        }


    def clear_imported(self, provider_name: str | None = None, write: bool = False, include_curated: bool = False) -> dict[str, Any]:
        from .config import dump_yaml

        curated_models = _dict_of_dicts(self.config.get("models", {}))
        generated_models = _dict_of_dicts(self.generated_config.get("models", {}))
        removed_counts: dict[str, int] = {}
        removed_curated_counts: dict[str, int] = {}
        curated_dirty = False
        generated_dirty = False
        for name, model in list(generated_models.items()):
            if not isinstance(model, dict):
                continue
            source = model_source(model)
            if provider_name and source != provider_name:
                continue
            removed_counts[source] = removed_counts.get(source, 0) + 1
            if write:
                generated_models.pop(name, None)
                generated_dirty = True
        for name, model in list(curated_models.items()):
            if not isinstance(model, dict):
                continue
            is_imported = _is_refresh_imported_model(model)
            if not is_imported and not include_curated:
                continue
            source = model_source(model)
            if provider_name and source != provider_name:
                continue
            removed_counts[source] = removed_counts.get(source, 0) + 1
            if not is_imported:
                removed_curated_counts[source] = removed_curated_counts.get(source, 0) + 1
            if write:
                curated_models.pop(name, None)
                curated_dirty = True
        total_removed = sum(removed_counts.values())
        if write and total_removed:
            self.config["models"] = curated_models
            self.generated_config["models"] = generated_models
            if curated_dirty:
                (self.profile.root / "models.yaml").write_text(dump_yaml(self.config), encoding="utf-8")
            if generated_dirty:
                self._write_generated_config()
        provider_counts = [{"name": source, "count": count} for source, count in sorted(removed_counts.items())]
        curated_provider_counts = [{"name": source, "count": count} for source, count in sorted(removed_curated_counts.items())]
        return {
            "name": "model_catalog_clear_cache",
            "write": write,
            "provider": provider_name,
            "include_curated": include_curated,
            "removed": total_removed if write else 0,
            "would_remove": 0 if write else total_removed,
            "provider_counts": provider_counts,
            "curated_provider_counts": curated_provider_counts,
            "path": str(self.profile.root / "models.yaml"),
            "generated_path": str(self._generated_path()),
        }

    def _generated_path(self) -> Path:
        return self.profile.root / GENERATED_MODELS_FILE

    def _load_generated_config(self) -> dict[str, Any]:
        from .config import parse_yaml

        path = self._generated_path()
        if not path.exists():
            return {}
        data = parse_yaml(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _write_generated_config(self) -> Path:
        from .config import dump_yaml

        path = self._generated_path()
        path.write_text(dump_yaml(self.generated_config), encoding="utf-8")
        return path


    def pull_plan(self, name: str | None = None, source: str | None = None, model_id: str | None = None, for_runtime: str | None = None, file: str | None = None) -> dict[str, Any]:
        if name:
            model = self.get(name)
            source = source or model_source(model)
            model_id = model_id or str(model.get("model") or "")
            for_runtime = for_runtime or str(model.get("preferred_runtime") or model.get("provider") or "")
        if not source or not model_id:
            raise ValueError("pull planning requires a model alias, or both --source and --model-id")
        command: list[str]
        if source == "ollama":
            command = ["ollama", "pull", model_id]
        elif source == "huggingface":
            command = ["python", "-c", f"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')"]
        elif source == "huggingface_gguf":
            if file:
                command = ["python", "-c", f"from huggingface_hub import hf_hub_download; hf_hub_download('{model_id}', filename='{file}')"]
            else:
                command = ["python", "-c", f"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')"]
        elif source == "civitai":
            command = ["python", "-m", "aiplane", "providers", "models", "civitai", "--online", "--query", model_id]
        elif source == "modelscope":
            command = ["provider-native-pull", "modelscope", model_id]
        elif source == "piper_voices":
            command = ["provider-native-pull", "piper_voices", model_id]
        elif source == "local_file":
            command = ["test", "-f", model_id]
        else:
            command = ["provider-native-pull", source, model_id]
        return {"name": name, "source": source, "model": model_id, "runtime": for_runtime, "file": file, "command": command}

    def get(self, name: str) -> dict[str, Any]:
        models = self.models()
        if name not in models:
            raise ValueError(f"unknown model: {name}")
        return models[name]

    def show(self, name: str) -> dict[str, Any]:
        model = {"name": name, **dict(self.get(name))}
        provider_name = str(model.get("provider", ""))
        provider = self.providers().get(provider_name, {})
        model["source"] = model_source(model)
        model["ownership"] = ownership_for_model(model, provider)
        model["runtime"] = model.get("preferred_runtime") or provider.get("runtime") or provider_name
        model["provider_config"] = provider
        model["capabilities"] = capability_profile(model)
        model["capability_avg_score"] = _capability_average(model["capabilities"])
        from .benchmarks import latest_benchmark_summary

        model["latest_benchmark"] = latest_benchmark_summary(self.profile, name)
        model["capability_tags"] = capability_tags(model["capabilities"])
        model["top_capabilities"] = top_capabilities(model["capabilities"])
        return model

    def doctor(self) -> list[ModelStatus]:
        statuses = []
        for name, model in self.models().items():
            statuses.append(self._status(name, model))
        return statuses

    def pull(self, name: str) -> str:
        model = self.get(name)
        if model.get("provider") != "ollama":
            raise ValueError("pull is only supported for Ollama models")
        model_id = str(model.get("model"))
        result = subprocess.run(["ollama", "pull", model_id], cwd=self.profile.workspace, text=True, capture_output=True, check=False)
        output = (result.stdout + result.stderr).strip()
        if result.returncode:
            raise RuntimeError(output or f"ollama pull failed for {model_id}")
        return output

    def complete(self, name: str, prompt: str) -> BackendResult:
        model = self.get(name)
        provider_name = self._runtime_for_model(name, model)
        if provider_name in {"ollama", "ollama_cloud"}:
            return self._ollama_backend(provider_name).chat(str(model.get("model")), prompt)
        if self._is_openai_compatible(provider_name):
            return self._openai_compatible_backend(provider_name).chat(str(model.get("model")), prompt)
        raise ValueError(f"execution is not wired for runtime/provider: {provider_name}")

    def _runtime_for_model(self, name: str, model: dict[str, Any]) -> str:
        from .runtime_catalog import RuntimeCatalog

        runtime_catalog = RuntimeCatalog(self.profile)
        selection = runtime_catalog.select_runtime(name)
        preferred = str(model.get("preferred_runtime") or model.get("provider") or "")
        if selection["available"] and selection["selected"]:
            return str(selection["selected"])
        supported = ", ".join(selection["supported_runtimes"]) or preferred or "none"
        details = "; ".join(f"{status['name']}: {status['reason']}" for status in selection["statuses"])
        raise RuntimeError(f"No supported runtime is running for model {name}. Supported runtimes: {supported}. {details}")

    def _ollama_backend(self, provider_name: str) -> OllamaBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = str(provider.get("endpoint", "http://localhost:11434" if provider_name == "ollama" else "https://ollama.com"))
        timeout = int(provider.get("timeout_seconds", 60))
        headers = {}
        key_env = provider.get("api_key_env")
        if key_env and os.environ.get(str(key_env)):
            headers["Authorization"] = "Bearer " + os.environ[str(key_env)]
        return OllamaBackend(endpoint, timeout, headers)

    def _openai_compatible_backend(self, provider_name: str) -> OpenAICompatibleBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = self._openai_compatible_endpoint(provider_name, provider)
        timeout = int(provider.get("timeout_seconds", 60))
        headers = {}
        key_env = provider.get("api_key_env")
        if key_env and os.environ.get(str(key_env)):
            headers["Authorization"] = "Bearer " + os.environ[str(key_env)]
        return OpenAICompatibleBackend(endpoint, timeout, headers)

    def _openai_compatible_endpoint(self, provider_name: str, provider: dict[str, Any] | None = None) -> str:
        provider = provider or self.providers().get(provider_name, {})
        endpoint = str(provider.get("endpoint", ""))
        if not endpoint and provider_name == "openai":
            endpoint = "https://api.openai.com/v1"
        if not endpoint:
            raise ValueError(f"provider {provider_name!r} is missing endpoint")
        return endpoint.rstrip("/")

    def _is_openai_compatible(self, provider_name: str) -> bool:
        provider = self.providers().get(provider_name, {})
        protocol = str(provider.get("protocol", ""))
        return protocol == "openai_compatible" or provider_name in {"vllm", "lmstudio", "llamacpp", "tgi", "localai", "openai"}

    def test_prompt(self, name: str, task: str, target: Path | None = None, dry_run: bool = False) -> BackendResult:
        model = self.get(name)
        prompt = build_smoke_prompt(task, target)
        if dry_run:
            return BackendResult("dry_run", prompt, False)
        provider_name = str(model.get("provider"))
        if provider_name not in {"ollama", "ollama_cloud"} and not self._is_openai_compatible(provider_name):
            raise ValueError("model test cannot execute this provider yet; use --dry-run or configure an OpenAI-compatible endpoint")
        return self.complete(name, prompt)

    def _status(self, name: str, model: dict[str, Any]) -> ModelStatus:
        provider_name = str(model.get("provider", ""))
        provider = self.providers().get(provider_name, {})
        if not bool(model.get("enabled", True)):
            return ModelStatus(name, provider_name, True, False, "model is disabled")
        if provider_name in {"ollama", "ollama_cloud"}:
            if provider_name == "ollama_cloud" and provider.get("api_key_env") and not os.environ.get(str(provider.get("api_key_env"))):
                return ModelStatus(name, provider_name, True, False, f"missing env var {provider.get('api_key_env')}")
            backend = self._ollama_backend(provider_name)
            reachable, reason = backend.is_reachable()
            if not reachable:
                return ModelStatus(name, provider_name, True, False, reason)
            model_id = str(model.get("model", ""))
            try:
                pulled = model_id in backend.available_models()
            except Exception as exc:  # pragma: no cover - defensive after reachability check
                return ModelStatus(name, provider_name, True, False, str(exc))
            return ModelStatus(name, provider_name, True, pulled, "model is pulled" if pulled else f"model is not pulled: ollama pull {model_id}")
        if self._is_openai_compatible(provider_name):
            key_env = provider.get("api_key_env")
            if key_env and not os.environ.get(str(key_env)):
                return ModelStatus(name, provider_name, True, False, f"missing env var {key_env}")
            if not bool(provider.get("enabled", True)):
                return ModelStatus(name, provider_name, True, False, "provider is disabled")
            backend = self._openai_compatible_backend(provider_name)
            reachable, reason = backend.is_reachable()
            if not reachable:
                return ModelStatus(name, provider_name, True, False, reason)
            model_id = str(model.get("model", ""))
            try:
                available = backend.available_models()
            except Exception as exc:  # pragma: no cover - defensive after reachability check
                return ModelStatus(name, provider_name, True, False, str(exc))
            usable = not available or model_id in available
            return ModelStatus(name, provider_name, True, usable, "model is available" if usable else f"model was not listed by provider: {model_id}")
        key_env = provider.get("api_key_env")
        if key_env:
            present = bool(os.environ.get(str(key_env)))
            return ModelStatus(name, provider_name, True, present, f"env var {key_env} is present" if present else f"missing env var {key_env}")
        return ModelStatus(name, provider_name, bool(provider), False, "provider has no usable local check yet")



def capability_profile(model: dict[str, Any]) -> dict[str, Any]:
    configured = model.get("capability_scores")
    if isinstance(configured, dict):
        scores = {key: _int_or_zero(value) for key, value in configured.items()}
        source = str(model.get("capability_score_source", "configured"))
    else:
        scores = _heuristic_capability_scores(model)
        source = "catalog_heuristic"
    return {
        "score_scale": "0-5",
        "score_source": source,
        "scores": scores,
        "benchmark_refs": _benchmark_refs(model),
        "notes": "Scores are suitability signals, not absolute benchmark percentages.",
    }


def _heuristic_capability_scores(model: dict[str, Any]) -> dict[str, int]:
    model_id = str(model.get("model", "")).lower()
    roles = {str(role) for role in model.get("roles", []) if role}
    params = _parameter_billions(model_id)
    is_cloud = not bool(model.get("local", False))
    is_embedding = "embed" in model_id or "embedding" in roles
    is_code = any(token in model_id for token in ["coder", "code", "starcoder", "codellama"]) or "completion" in roles
    is_reasoning = "deepseek-r1" in model_id or "reason" in model_id
    is_general = any(token in model_id for token in ["llama", "hermes", "gpt", "claude", "qwen2.5"])

    if is_embedding:
        return {
            "code_analysis": 0,
            "code_generation": 0,
            "code_completion": 0,
            "debugging_refactor": 0,
            "reasoning": 0,
            "math": 0,
            "tool_use": 0,
            "general_chat": 0,
            "embedding": 5,
            "vision_image_understanding": 0,
            "image_generation": 0,
            "audio": 0,
            "video": 0,
        }

    code_base = 1
    if is_code:
        code_base = 2 + _size_bonus(params)
    elif is_reasoning or is_general:
        code_base = 1 + min(_size_bonus(params), 2)
    if is_cloud:
        code_base = max(code_base, 4)

    reasoning = 1 + min(_size_bonus(params), 3)
    if is_reasoning:
        reasoning = min(5, reasoning + 1)
    if is_cloud:
        reasoning = max(reasoning, 4)

    instruction = 2 + min(_size_bonus(params), 2)
    if is_cloud:
        instruction = max(instruction, 4)

    completion = code_base if "completion" in roles or is_code else max(1, code_base - 1)

    return {
        "code_analysis": _clamp(code_base),
        "code_generation": _clamp(code_base),
        "code_completion": _clamp(completion),
        "debugging_refactor": _clamp(code_base - (0 if params >= 14 else 1)),
        "reasoning": _clamp(reasoning),
        "math": _clamp(reasoning if is_reasoning else reasoning - 1),
        "tool_use": _clamp(instruction if params >= 7 or is_cloud else instruction - 1),
        "general_chat": _clamp(instruction),
        "embedding": 0,
        "vision_image_understanding": 0,
        "image_generation": 0,
        "audio": 0,
        "video": 0,
    }


def _benchmark_refs(model: dict[str, Any]) -> list[str]:
    model_id = str(model.get("model", "")).lower()
    refs = []
    if any(token in model_id for token in ["coder", "code", "starcoder", "codellama"]):
        refs.extend(["HumanEval", "MBPP", "LiveCodeBench", "SWE-bench-style repair tasks"])
    if "deepseek-r1" in model_id:
        refs.extend(["AIME", "MATH", "GPQA", "Codeforces", "LiveCodeBench"])
    if any(token in model_id for token in ["llama", "hermes", "gpt", "claude"]):
        refs.extend(["MMLU/MMLU-Pro", "GPQA", "IFEval", "Arena-style preference evals"])
    if not refs:
        refs.append("catalog heuristic; no specific benchmark reference configured")
    return list(dict.fromkeys(refs))


def _parameter_billions(model_id: str) -> float:
    import re

    matches = re.findall(r"(\d+(?:\.\d+)?)\s*b", model_id)
    if not matches:
        return 0.0
    try:
        return float(matches[-1])
    except ValueError:
        return 0.0


def _size_bonus(params: float) -> int:
    if params >= 70:
        return 3
    if params >= 30:
        return 3
    if params >= 14:
        return 2
    if params >= 7:
        return 1
    return 0


def _clamp(value: int) -> int:
    return max(0, min(5, int(value)))


def _int_or_zero(value: object) -> int:
    try:
        return _clamp(int(value))
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    text = str(value)
    return [text] if text else []


def _benchmark_score(row: dict[str, Any]) -> float:
    benchmark = row.get("latest_benchmark")
    if not isinstance(benchmark, dict):
        return 0.0
    try:
        return float(benchmark.get("average_score", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _role_score_for_row(row: dict[str, Any], roles: list[str]) -> float:
    if not roles:
        return 0.0
    scores = row.get("capabilities", {}).get("scores", {}) if isinstance(row.get("capabilities"), dict) else {}
    role_scores: list[float] = []
    for role in roles:
        capabilities = ROLE_CAPABILITY_MAP.get(role, [])
        if not capabilities:
            continue
        role_scores.append(sum(float(scores.get(capability, 0) or 0) for capability in capabilities) / len(capabilities))
    if not role_scores:
        return 0.0
    return round(sum(role_scores) / len(role_scores), 2)


def _recommendation_row(row: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    payload = dict(row)
    if roles:
        payload["matched_roles"] = [role for role in roles if role in row.get("roles", [])]
        payload["role_score"] = _role_score_for_row(row, roles)
        payload["role_capabilities"] = {role: ROLE_CAPABILITY_MAP.get(role, []) for role in roles}
    else:
        payload["role_score"] = None
    return payload


ROLE_CAPABILITY_MAP: dict[str, list[str]] = {
    "chat": ["general_chat", "reasoning", "tool_use"],
    "autocomplete": ["code_completion"],
    "embedding": ["embedding"],
    "analysis": ["code_analysis", "reasoning"],
    "generation": ["code_generation", "general_chat"],
    "refactor": ["debugging_refactor", "code_analysis"],
}

CAPABILITY_ALIASES: dict[str, list[str]] = {
    "coding": ["code_generation", "code_analysis", "code_completion"],
    "autocomplete": ["code_completion"],
    "debugging": ["debugging_refactor"],
    "reasoning": ["reasoning"],
    "chat": ["general_chat"],
    "embedding": ["embedding"],
    "tool_use": ["tool_use"],
    "stt": ["speech_to_text", "audio"],
    "tts": ["text_to_speech", "audio"],
    "image": ["image_generation", "vision_image_understanding"],
    "video": ["video_generation", "video"],
}


def top_capabilities(profile: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    scores = profile.get("scores", {}) if isinstance(profile, dict) else {}
    rows = [{"name": name, "score": score} for name, score in scores.items() if isinstance(score, int) and score > 0]
    return sorted(rows, key=lambda row: (-int(row["score"]), str(row["name"])))[:limit]


def capability_tags(profile: dict[str, Any], minimum: int = 3) -> list[str]:
    scores = profile.get("scores", {}) if isinstance(profile, dict) else {}
    tags = []
    for tag, keys in CAPABILITY_ALIASES.items():
        values = [int(scores.get(key, 0)) for key in keys]
        if values and max(values) >= minimum:
            tags.append(tag)
    return tags


def model_source(model: dict[str, Any]) -> str:
    if model.get("source"):
        return str(model.get("source"))
    provider = str(model.get("provider", ""))
    model_id = str(model.get("model", ""))
    if provider in {"ollama", "ollama_cloud"}:
        return "ollama"
    if provider in {"vllm", "tgi", "transformers"} or "/" in model_id:
        return "huggingface"
    if provider in {"llamacpp", "localai"} or model_id.endswith(".gguf"):
        return "huggingface_gguf"
    if provider in {"openai", "anthropic", "azure_openai"}:
        return "managed_catalog"
    return provider or "unknown"


def ownership_for_model(model: dict[str, Any], provider: dict[str, Any]) -> str:
    if model.get("ownership"):
        return str(model.get("ownership"))
    if provider.get("ownership"):
        return str(provider.get("ownership"))
    provider_name = str(model.get("provider", ""))
    if provider_name in {"openai", "anthropic", "azure_openai", "ollama_cloud"}:
        return "managed_service"
    return "self_managed"


def parse_capability_filter(value: str) -> tuple[str, int]:
    for operator in [">=", ":"]:
        if operator in value:
            name, threshold = value.split(operator, 1)
            return name.strip(), _clamp(int(threshold.strip()))
    return value.strip(), 1


def expand_capability_filters(values: list[str]) -> dict[str, int]:
    expanded: dict[str, int] = {}
    for value in values:
        name, threshold = parse_capability_filter(value)
        keys = CAPABILITY_ALIASES.get(name, [name])
        for key in keys:
            expanded[key] = max(expanded.get(key, 0), threshold)
    return expanded


def _capability_average(profile: dict[str, Any]) -> float:
    scores = profile.get("scores", {}) if isinstance(profile, dict) else {}
    values = [int(value) for value in scores.values() if isinstance(value, int)]
    return round(sum(values) / len(values), 2) if values else 0.0



def _refresh_status(changes: dict[str, int]) -> str:
    if int(changes.get("imported", 0)) > 0 or int(changes.get("updated", 0)) > 0 or int(changes.get("removed", 0)) > 0:
        return "updated"
    if int(changes.get("would_import", 0)) > 0 or int(changes.get("would_update", 0)) > 0 or int(changes.get("would_remove", 0)) > 0:
        return "would_update"
    return "ok"


def _refresh_model_row(name: str, model: dict[str, Any], runtime_catalog: Any, refresh_status: str, provider_visible: bool | None, provider_reason: str) -> dict[str, Any]:
    source = runtime_catalog.source_for_model(model)
    preferred = model.get("preferred_runtime") or model.get("provider")
    provider_name = str(model.get("provider") or "")
    providers = runtime_catalog.models_config.get("providers", {}) if isinstance(runtime_catalog.models_config, dict) else {}
    provider = providers.get(provider_name, {}) if isinstance(providers, dict) else {}
    ownership = ownership_for_model(model, provider)
    row = {
        "name": name,
        "model": {"id": model.get("model"), "source": source},
        "runtime_endpoint": provider_name,
        "ownership": ownership,
        "refresh_status": refresh_status,
        "enabled": bool(model.get("enabled", True)),
        "provider_visible": provider_visible,
        "local_presence": _refresh_local_presence(ownership, provider_name, provider_visible),
        "provider_reason": provider_reason,
        "preferred_runtime": preferred,
        "suitable_runtimes": runtime_catalog.compatible_runtimes_for_entry(model),
    }
    for key in ["roles", "local", "api_key_env", "pull_command", "min_ram_gb", "recommended_ram_gb", "min_vram_gb", "recommended_vram_gb", "notes"]:
        if key in model and key not in row:
            row[key] = model[key]
    return row


def _refresh_local_presence(ownership: str, provider_name: str, provider_visible: bool | None) -> str:
    if ownership == "managed_service":
        return "not_applicable_managed_service"
    if provider_visible is True:
        return "present" if provider_name != "ollama" else "pulled"
    if provider_visible is False:
        return "not_listed" if provider_name != "ollama" else "not_pulled"
    return "not_checked"


def _group_refresh_catalog_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        ownership = str(row.get("ownership") or "unknown")
        provider = str((row.get("model") or {}).get("source") if isinstance(row.get("model"), dict) else row.get("source") or "unknown")
        grouped.setdefault(ownership, {}).setdefault(provider, []).append(row)
    return {
        ownership: {provider: sorted(items, key=lambda item: str(item.get("name") or "")) for provider, items in sorted(providers.items())}
        for ownership, providers in sorted(grouped.items())
    }


def _unique_model_alias(models: dict[str, Any], provider_name: str, model_id: str) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")
    if provider_name and not base.startswith(provider_name + "-"):
        base = f"{provider_name}-{base}"
    name = base or "model"
    suffix = 2
    while name in models:
        name = f"{base}-{suffix}"
        suffix += 1
    return name


def _discovered_model_entry(provider_name: str, model_id: str, enable: bool = False, source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    params = _parameter_billions(model_id.lower())
    roles = _roles_for_model_id(model_id)
    min_ram, recommended_ram, min_vram, recommended_vram = _resource_guess(params, roles)
    entry: dict[str, Any] = {
        "provider": _preferred_runtime_for_source(provider_name),
        "model": model_id,
        "roles": roles,
        "local": provider_name not in {"openai", "anthropic", "azure_openai", "ollama_cloud"},
        "enabled": enable,
        "source": provider_name,
        "preferred_runtime": _preferred_runtime_for_source(provider_name),
        "notes": "Discovered from model provider and imported into the editable profile catalog.",
        "imported_by": "aiplane_refresh",
        "min_ram_gb": min_ram,
        "recommended_ram_gb": recommended_ram,
        "min_vram_gb": min_vram,
        "source_metadata": source_metadata or {},
    }
    if recommended_vram is not None:
        entry["recommended_vram_gb"] = recommended_vram
    if provider_name == "ollama":
        entry["pull_command"] = f"ollama pull {model_id}"
    elif provider_name == "huggingface":
        entry["pull_command"] = f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')\""
    elif provider_name == "huggingface_gguf":
        entry["pull_command"] = f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')\""
    elif provider_name == "civitai":
        entry["pull_command"] = "download via Civitai model/version API and place checkpoint in the target runtime model directory"
    if "embedding" in roles:
        entry["capability_scores"] = _heuristic_capability_scores(entry)
        entry["capability_score_source"] = "catalog_heuristic"
    return entry



def _merge_source_discovered_model(existing: dict[str, Any], provider_name: str, model_id: str, source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(existing)
    discovered = _discovered_model_entry(provider_name, model_id, enable=bool(existing.get("enabled", True)), source_metadata=source_metadata or {})
    source_fields = [
        "model",
        "source",
        "local",
        "pull_command",
        "source_metadata",
    ]
    if _is_refresh_imported_model(existing):
        source_fields.extend([
            "provider",
            "preferred_runtime",
            "roles",
            "notes",
            "imported_by",
            "min_ram_gb",
            "recommended_ram_gb",
            "min_vram_gb",
            "recommended_vram_gb",
        ])
        if "capability_scores" not in existing and "capability_scores" in discovered:
            source_fields.extend(["capability_scores", "capability_score_source"])
    for field in source_fields:
        if field in discovered:
            merged[field] = discovered[field]
        elif field in {"recommended_vram_gb"} and field in merged:
            merged.pop(field, None)
    return merged

def _is_refresh_imported_model(model: dict[str, Any]) -> bool:
    if model.get("imported_by") == "aiplane_refresh":
        return True
    notes = str(model.get("notes") or "")
    return notes.startswith("Discovered from model provider") or notes.startswith("Discovered from provider")


def _preferred_runtime_for_source(provider_name: str) -> str:
    if provider_name == "ollama":
        return "ollama"
    if provider_name == "huggingface":
        return "vllm"
    if provider_name == "huggingface_gguf":
        return "llamacpp"
    if provider_name == "civitai":
        return "comfyui"
    if provider_name == "piper_voices":
        return "piper"
    if provider_name == "modelscope":
        return "transformers"
    return provider_name


def _roles_for_model_id(model_id: str) -> list[str]:
    value = model_id.lower()
    if "embed" in value:
        return ["embedding"]
    if any(token in value for token in ["whisper", "stt", "speech-to-text"]):
        return ["speech_to_text"]
    if any(token in value for token in ["tts", "text-to-speech"]):
        return ["text_to_speech"]
    if any(token in value for token in ["vision", "vl", "llava"]):
        return ["chat", "analysis", "vision"]
    if "coder" in value or "code" in value:
        if "base" in value:
            return ["completion", "autocomplete"]
        return ["analysis", "completion", "autocomplete", "generation"]
    return ["chat", "analysis", "generation"]


def _resource_guess(params: float, roles: list[str]) -> tuple[int, int, int, int | None]:
    if "embedding" in roles:
        return 4, 8, 0, None
    if params <= 0:
        return 8, 16, 0, None
    if params <= 2:
        return 8, 16, 0, None
    if params <= 4:
        return 12, 24, 0, 4
    if params <= 9:
        return 16, 32, 6, 10
    if params <= 16:
        return 32, 64, 12, 16
    if params <= 35:
        return 64, 128, 24, 32
    return 128, 256, 48, 80


def _number_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_smoke_prompt(task: str, target: Path | None = None) -> str:
    task = task.lower().strip()
    if task not in {"analysis", "completion", "write"}:
        raise ValueError("task must be one of: analysis, completion, write")
    source = ""
    if target is not None:
        source = target.read_text(encoding="utf-8")
    if task == "analysis":
        return "Explain what this code does, identify one risk, and suggest one small improvement.\n\n```python\n" + source + "\n```"
    if task == "completion":
        return "Complete the following Python function. Return only code.\n\n```python\ndef add_numbers(a, b):\n" + (source or "    ") + "\n```"
    return "Write a small Python function named is_even(value) and a unittest test case for it. Return only code."


def _dict_of_dicts(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): inner for key, inner in value.items() if isinstance(inner, dict)}
