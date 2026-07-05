from __future__ import annotations

from typing import Any

from .models import Profile
from .runtime_catalog import RuntimeCatalog

SUPPORTED_PULL_SOURCES: dict[str, list[str]] = {
    "ollama": ["ollama", "huggingface_gguf"],
    "vllm": ["huggingface", "nvidia"],
    "tgi": ["huggingface", "nvidia"],
    "transformers": ["huggingface", "nvidia"],
}


def runtime_model_id(profile: Profile, runtime: str, model: dict[str, Any]) -> str:
    model_id = str(model.get("model") or "")
    if runtime != "ollama":
        return model_id
    return ollama_model_id(profile, model) or model_id


def ollama_model_id(profile: Profile, model: dict[str, Any]) -> str:
    runtime_catalog = RuntimeCatalog(profile)
    provider = str(model.get("provider") or "")
    source = runtime_catalog.source_for_model(model)
    model_id = str(model.get("model") or "")
    supported = runtime_catalog.compatible_runtimes_for_entry(model, include_gui=True)
    if provider == "ollama":
        return model_id
    if source == "huggingface_gguf" and "ollama" in supported:
        if model_id.startswith("hf.co/"):
            return model_id
        if model_id.startswith(("http://", "https://")):
            return ""
        if "/" in model_id:
            return f"hf.co/{model_id}"
    return ""


def runtime_pull_support(runtime: str, selected: dict[str, Any]) -> dict[str, Any]:
    provider = str(selected.get("provider") or "")
    source = str(selected.get("source") or provider)
    runtime_model = str(selected.get("model") or "")
    if runtime == "llamacpp":
        if runtime_model.startswith(
            ("http://", "https://")
        ) and runtime_model.lower().endswith(".gguf"):
            return {"supported": True, "supported_sources": ["direct_gguf_url"]}
        return {
            "supported": False,
            "supported_sources": ["direct_gguf_url"],
            "reason": (
                "llama.cpp setup can only pull direct GGUF URLs; use a direct .gguf URL, "
                "preconfigure LLAMACPP_MODEL_PATH, or download the file manually"
            ),
        }
    allowed = SUPPORTED_PULL_SOURCES.get(runtime, [])
    if source in allowed or provider in allowed:
        return {"supported": True, "supported_sources": allowed}
    if runtime in {"localai", "lmstudio"}:
        return {
            "supported": False,
            "supported_sources": [],
            "reason": f"{runtime} model downloads are manual or runtime-specific in this milestone",
        }
    return {
        "supported": False,
        "supported_sources": allowed,
        "reason": f"aiplane does not currently know how to pull source {source!r} through runtime {runtime!r}",
    }
