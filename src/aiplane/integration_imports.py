"""Secret-free imports from supported client configuration files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .config import create_profile, dump_yaml, parse_yaml, profiles_root
from .persistence import atomic_write_text, file_lock

_ENV_REF = re.compile(r"^(?:\$\{([A-Z][A-Z0-9_]*)\}|\$([A-Z][A-Z0-9_]*))$")
_ALIAS = re.compile(r"[^a-z0-9]+")


def import_client_config(
    tool: str,
    source_path: Path,
    *,
    profile_name: str,
    template: str = "local-dev",
    profiles_dir: Path | None = None,
    yes: bool = False,
) -> dict[str, Any]:
    if tool not in {"continue", "aider"}:
        raise ValueError("client import supports continue and aider")
    source_path = source_path.expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"config file not found: {source_path}")
    destination = profiles_root(profiles_dir) / profile_name
    if destination.exists():
        raise ValueError(f"profile already exists: {profile_name}")

    config = _load_client_config(source_path)
    candidates = _continue_models(config) if tool == "continue" else _aider_models(config)
    if not candidates:
        raise ValueError(f"no supported model entries found in {tool} config")
    models, redacted, warnings = _normalize_models(candidates)
    result = {
        "source_tool": tool,
        "profile": profile_name,
        "template": template,
        "destination": str(destination),
        "status": "unapproved",
        "models": models,
        "redacted_fields": sorted(redacted),
        "warnings": sorted(set(warnings)),
        "preview": not yes,
        "written": False,
        "next_steps": [
            f"aiplane profiles validate {profile_name}",
            f"aiplane models list --profile {profile_name}",
            "Review imported model ids, providers, endpoints, and credential environment references before approval.",
        ],
    }
    if not yes:
        return result

    profile_root = profiles_root(profiles_dir)
    profile_root.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=".aiplane-import-", dir=profile_root))
    try:
        staged_profile = create_profile(profile_name, template=template, profiles_dir=staging_root)
        model_path = staged_profile / "models.yaml"
        model_document = parse_yaml(model_path.read_text(encoding="utf-8"))
        model_document["models"] = models
        atomic_write_text(model_path, dump_yaml(model_document))

        repository_path = staged_profile / "repository.yaml"
        repository = parse_yaml(repository_path.read_text(encoding="utf-8"))
        repository["import_review"] = {
            "status": "unapproved",
            "source_tool": tool,
            "secrets_copied": False,
            "review_required": True,
        }
        atomic_write_text(repository_path, dump_yaml(repository))
        with file_lock(profile_root / ".profile-import"):
            if destination.exists():
                raise ValueError(f"profile already exists: {profile_name}")
            os.rename(staged_profile, destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
    result["preview"] = False
    result["written"] = True
    return result


def _load_client_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _parse_client_yaml(text)
    if not isinstance(payload, dict):
        raise ValueError("client config must be a JSON or YAML object")
    return payload


def _parse_client_yaml(text: str) -> dict[str, Any]:
    # Continue uses a top-level models list, which the core profile YAML subset
    # intentionally does not need. Parse just that client-owned shape here.
    result: dict[str, Any] = {}
    current_list: list[dict[str, Any]] | None = None
    current_item: dict[str, Any] | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            key = stripped[:-1].strip()
            if key == "models":
                current_list = []
                result[key] = current_list
            continue
        if stripped.startswith("- "):
            if current_list is None:
                continue
            current_item = {}
            current_list.append(current_item)
            stripped = stripped[2:].strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        value = raw_value.strip().strip('"').strip("'")
        target = current_item if current_item is not None and raw.startswith((" ", "\t")) else result
        target[key.strip()] = value
    return result


def _continue_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_models = config.get("models")
    if not isinstance(raw_models, list):
        return []
    return [
        {
            "alias": item.get("name") or item.get("title"),
            "id": item.get("model"),
            "provider": item.get("provider"),
            "endpoint": item.get("apiBase") or item.get("baseUrl"),
            "credential": item.get("apiKey"),
            "role": "chat",
        }
        for item in raw_models
        if isinstance(item, dict)
    ]


def _aider_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    endpoint = config.get("openai-api-base") or config.get("openai_api_base")
    credential = config.get("openai-api-key") or config.get("openai_api_key")
    result = []
    for key, role in (("model", "chat"), ("weak-model", "chat"), ("editor-model", "code")):
        value = config.get(key) or config.get(key.replace("-", "_"))
        if value:
            provider, model_id = _split_aider_model(str(value))
            result.append(
                {
                    "alias": key.replace("-model", "") or "chat",
                    "id": model_id,
                    "provider": provider,
                    "endpoint": endpoint,
                    "credential": credential,
                    "role": role,
                }
            )
    return result


def _split_aider_model(value: str) -> tuple[str, str]:
    if "/" not in value:
        return "openai", value
    prefix, model_id = value.split("/", 1)
    aliases = {"ollama_chat": "ollama", "ollama": "ollama", "openai": "openai", "anthropic": "anthropic"}
    return aliases.get(prefix, prefix), model_id


def _normalize_models(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any], set[str], list[str]]:
    models: dict[str, Any] = {}
    redacted: set[str] = set()
    warnings: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        model_id = str(candidate.get("id") or "").strip()
        if not model_id:
            continue
        provider = str(candidate.get("provider") or "openai").strip().lower().replace("-", "_")
        alias_base = str(candidate.get("alias") or model_id)
        alias = _ALIAS.sub("-", alias_base.lower()).strip("-") or f"imported-{index}"
        while alias in models:
            alias = f"{alias}-{index}"
        runtime = provider if provider in {"ollama", "vllm", "llamacpp", "lmstudio", "docker_model_runner"} else None
        item: dict[str, Any] = {
            "provider": provider,
            "model": model_id,
            "source": provider,
            "roles": [str(candidate.get("role") or "chat")],
        }
        if runtime:
            item["supported_runtimes"] = [runtime]
            item["preferred_runtime"] = runtime
        endpoint = candidate.get("endpoint")
        if endpoint:
            item["endpoint"] = str(endpoint)
        credential = candidate.get("credential")
        if credential:
            match = _ENV_REF.fullmatch(str(credential).strip())
            if match:
                item["api_key_env"] = match.group(1) or match.group(2)
            else:
                redacted.add(f"models.{alias}.credential")
                warnings.append(f"omitted a literal credential from imported model {alias}")
        models[alias] = item
    return models, redacted, warnings
