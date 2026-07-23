from __future__ import annotations

from typing import Any

from .model_resources import number_or_none as _number_or_none


def _preferred_runtime_for_source(provider_name: str) -> str:
    if provider_name == "ollama":
        return "ollama"
    if provider_name == "huggingface":
        return "vllm"
    if provider_name == "huggingface_gguf":
        return "llamacpp"
    if provider_name == "civitai":
        return "comfyui"
    if provider_name == "azure_speech":
        return "azure_speech"
    if provider_name == "elevenlabs":
        return "elevenlabs"
    if provider_name == "modelscope":
        return "transformers"
    return provider_name


def preferred_runtime_for_discovered_roles(provider_name: str, roles: list[str]) -> str:
    role_set = set(roles)
    if "video_generation" in role_set or "image_generation" in role_set:
        return "diffusers"
    if "speech_to_text" in role_set:
        return "faster_whisper"
    if "text_to_speech" in role_set:
        if provider_name in {"azure_speech", "elevenlabs"}:
            return provider_name
        return "transformers"
    return _preferred_runtime_for_source(provider_name)


def supported_runtimes_for_discovered_roles(roles: list[str]) -> list[str]:
    role_set = set(roles)
    if "video_generation" in role_set or "image_generation" in role_set:
        return ["diffusers", "comfyui"]
    if "speech_to_text" in role_set:
        return ["faster_whisper", "transformers"]
    if "text_to_speech" in role_set:
        return ["transformers"]
    return []


def resource_requirements_from_source_metadata(source_metadata: dict[str, Any]) -> dict[str, float | str]:
    if not isinstance(source_metadata, dict):
        return {}
    candidates: list[dict[str, Any]] = [source_metadata]
    for key in ["resources", "resource_requirements", "requirements", "hardware"]:
        value = source_metadata.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    def _first_number(keys: list[str]) -> float | None:
        for block in candidates:
            for key in keys:
                value = _number_or_none(block.get(key))
                if value is not None:
                    return value
        return None

    min_ram = _first_number(["min_ram_gb", "minimum_ram_gb"])
    rec_ram = _first_number(["recommended_ram_gb"])
    min_vram = _first_number(["min_vram_gb", "minimum_vram_gb"])
    rec_vram = _first_number(["recommended_vram_gb"])
    if all(value is None for value in [min_ram, rec_ram, min_vram, rec_vram]):
        return {}
    source = None
    for block in candidates:
        value = block.get("resource_estimate_source")
        if isinstance(value, str) and value.strip():
            source = value.strip()
            break
    payload: dict[str, float | str] = {}
    if min_ram is not None:
        payload["min_ram_gb"] = min_ram
    if rec_ram is not None:
        payload["recommended_ram_gb"] = rec_ram
    if min_vram is not None:
        payload["min_vram_gb"] = min_vram
    if rec_vram is not None:
        payload["recommended_vram_gb"] = rec_vram
    if source:
        payload["resource_estimate_source"] = source
    return payload


def roles_for_discovered_model(provider_name: str, model_id: str, source_metadata: dict[str, Any]) -> list[str]:
    pipeline = str(source_metadata.get("pipeline_tag") or "").lower().strip()
    tags = (
        {str(tag).lower() for tag in source_metadata.get("tags", []) if tag}
        if isinstance(source_metadata.get("tags"), list)
        else set()
    )
    if pipeline in {"feature-extraction", "sentence-similarity"} or "sentence-transformers" in tags:
        return ["embedding"]
    if pipeline in {"automatic-speech-recognition", "audio-to-text"}:
        return ["speech_to_text"]
    if pipeline in {"text-to-speech"}:
        return ["text_to_speech"]
    if pipeline in {
        "text-to-image",
        "image-to-image",
        "unconditional-image-generation",
    }:
        return ["image_generation"]
    if pipeline in {"image-to-video", "text-to-video", "video-to-video"}:
        return ["video_generation"]
    if pipeline in {
        "image-classification",
        "object-detection",
        "image-segmentation",
        "zero-shot-image-classification",
    }:
        return ["image_classification"]
    if pipeline in {"visual-question-answering", "image-to-text"}:
        return ["analysis", "vision"]
    if pipeline in {"text-generation", "text2text-generation", "conversational"}:
        return _roles_for_model_id(model_id)
    if provider_name == "huggingface" and pipeline and not pipeline.startswith("text"):
        return [pipeline.replace("-", "_")]
    return _roles_for_model_id(model_id)


def _roles_for_model_id(model_id: str) -> list[str]:
    value = model_id.lower()
    if "embed" in value:
        return ["embedding"]
    if any(
        token in value
        for token in [
            "stt",
            "speech-to-text",
            "speech_to_text",
            "automatic-speech-recognition",
        ]
    ):
        return ["speech_to_text"]
    if any(token in value for token in ["tts", "text-to-speech"]):
        return ["text_to_speech"]
    if any(token in value for token in ["text-to-image", "texttoimage", "image-generation"]):
        return ["image_generation"]
    if any(token in value for token in ["text-to-video", "texttovideo", "video-generation", "t2v"]):
        return ["video_generation"]
    if any(token in value for token in ["vision", "visual", "image-to-text", "visual-question-answering"]):
        return ["chat", "analysis", "vision"]
    if "coder" in value or "code" in value:
        if "base" in value:
            return ["completion", "autocomplete"]
        return ["analysis", "completion", "autocomplete", "generation"]
    return ["chat", "analysis", "generation"]
