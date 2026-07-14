from __future__ import annotations

from typing import Any


class ModelRefreshCoordinator:
    """Reconcile provider discovery with curated and generated profile model state."""

    def run(
        self,
        catalog: Any,
        discovered: Any,
        provider_name: str,
        *,
        write: bool,
        enable: bool,
        online: bool,
        query: str | None,
        limit: int,
        verbose: bool,
    ) -> dict[str, Any]:
        from .model_catalog import (
            _dict_of_dicts,
            _discovered_model_entry,
            _is_refresh_imported_model,
            _merge_source_discovered_model,
            _refresh_model_row,
            _refresh_next_steps,
            _refresh_status,
            _unique_model_alias,
            model_source,
        )
        from .runtime_catalog import RuntimeCatalog

        runtime_catalog = RuntimeCatalog(catalog.profile)
        all_models = catalog.models()
        curated_models = _dict_of_dicts(catalog.config.get("models", {}))
        generated_models = _dict_of_dicts(catalog.generated_config.get("models", {}))
        provider_models = [model for model in all_models.values() if model_source(model) == provider_name]
        provider_imported_models = [model for model in provider_models if _is_refresh_imported_model(model)]
        provider_curated_models = [model for model in provider_models if not _is_refresh_imported_model(model)]
        existing_by_id = {
            str(model.get("model")): name
            for name, model in all_models.items()
            if model_source(model) == provider_name and model.get("model")
        }
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
                        changed_rows.append(
                            _refresh_model_row(
                                name,
                                merged,
                                runtime_catalog,
                                refresh_status=status,
                                provider_visible=True,
                                provider_reason=discovered.reason,
                            )
                        )
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
            changed_rows.append(
                _refresh_model_row(
                    name,
                    entry,
                    runtime_catalog,
                    refresh_status=status,
                    provider_visible=True,
                    provider_reason=discovered.reason,
                )
            )
            new_count += 1
            if write:
                generated_models[name] = entry
                all_models[name] = entry
                generated_dirty = True
                existing.add(model_id)
                existing_by_id[model_id] = name

        prune_enabled = (
            source_api_contacted
            and query is None
            and (discovered.source == "provider_api" or len(discovered.models) < int(limit))
        )
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
                changed_rows.append(
                    _refresh_model_row(
                        name,
                        model,
                        runtime_catalog,
                        refresh_status=status,
                        provider_visible=False,
                        provider_reason=discovered.reason,
                    )
                )
                remove_count += 1
                if write:
                    if name in generated_models:
                        generated_models.pop(name, None)
                        generated_dirty = True
                    elif name in curated_models:
                        curated_models.pop(name, None)
                        curated_dirty = True
                    all_models.pop(name, None)

        path = catalog.profile.root / "models.yaml"
        discovered_path = catalog._generated_path()
        if write and (curated_dirty or generated_dirty):
            catalog.config["models"] = curated_models
            catalog.generated_config["models"] = generated_models
            if curated_dirty:
                catalog.store.write_curated(catalog.config)
            if generated_dirty:
                catalog.store.write_generated(catalog.generated_config)

        changed_rows = sorted(
            changed_rows,
            key=lambda row: (
                str(row.get("runtime_endpoint")),
                str(row.get("refresh_status")),
                str(row.get("name")),
            ),
        )
        changes = {
            "imported": new_count if write else 0,
            "would_import": new_count if not write else 0,
            "updated": update_count if write else 0,
            "would_update": update_count if not write else 0,
            "removed": remove_count if write else 0,
            "would_remove": remove_count if not write else 0,
        }
        provider_config = catalog.providers().get(provider_name, {})
        provider_result = {
            "ownership": str(
                provider_config.get("ownership")
                or (
                    "managed_service"
                    if provider_name in {"openai", "anthropic", "azure_openai", "ollama_cloud"}
                    else "self_managed"
                )
            ),
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
            "discovered_path": str(discovered_path),
            "changes": changes,
            "results": {provider_name: provider_result},
            "next_steps": _refresh_next_steps(write, changes, provider_name=provider_name),
        }
