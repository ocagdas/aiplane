from __future__ import annotations

import importlib.util
import os
import platform
import shutil
from pathlib import Path
from typing import Any

from .backends import OllamaBackend, OpenAICompatibleBackend
from .config import dump_yaml, parse_yaml
from .models import Profile


RUNTIME_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ollama": {
        "description": "Local/headless Ollama runtime with its own model library and Modelfile/GGUF import path",
        "managed_by_helper": True,
        "gui_required": False,
        "protocol": "ollama_api",
        "model_sources": ["ollama", "gguf_import"],
        "good_for": ["simple local setup", "CPU laptop", "single-user workstation"],
        "install_hint": "scripts/provider_helper.sh --provider ollama --action install",
    },

    "azure_speech": {
        "description": "Azure AI Speech managed text-to-speech service",
        "managed_by_helper": False,
        "gui_required": False,
        "protocol": "azure_speech",
        "model_sources": ["azure_speech"],
        "good_for": ["managed text to speech", "demo narration", "cloud audio generation"],
        "install_hint": "Configure AZURE_SPEECH_KEY and AZURE_SPEECH_REGION, or use a credential reference in the profile.",
    },
    "vllm": {
        "description": "GPU-focused OpenAI-compatible server for Hugging Face Transformers-style models",
        "managed_by_helper": True,
        "gui_required": False,
        "protocol": "openai_compatible",
        "model_sources": ["huggingface"],
        "good_for": ["shared GPU workstation", "Azure/AWS GPU VM", "high-throughput inference"],
        "install_hint": "python -m pip install vllm",
    },
    "llamacpp": {
        "description": "llama.cpp server for GGUF models, good on CPU and modest GPUs",
        "managed_by_helper": "partial",
        "gui_required": False,
        "protocol": "openai_compatible",
        "model_sources": ["huggingface_gguf", "local_file"],
        "good_for": ["CPU laptop", "quantized local models", "portable shared VM"],
        "install_hint": "Install llama.cpp and put llama-server on PATH",
    },
    "tgi": {
        "description": "Hugging Face Text Generation Inference server for HF model repos",
        "managed_by_helper": True,
        "gui_required": False,
        "protocol": "openai_compatible",
        "model_sources": ["huggingface"],
        "good_for": ["server inference", "containerized GPU endpoints"],
        "install_hint": "Run the ghcr.io/huggingface/text-generation-inference container or native TGI install",
    },
    "transformers": {
        "description": "Hugging Face Transformers Python library for direct scripts, experiments, training, and fine-tuning",
        "managed_by_helper": "partial",
        "gui_required": False,
        "protocol": "python_library",
        "model_sources": ["huggingface"],
        "good_for": ["experiments", "training", "fine-tuning", "evaluation scripts"],
        "install_hint": "python -m pip install transformers accelerate torch",
    },
    "localai": {
        "description": "OpenAI-compatible local server that can run multiple backends, including GGUF/llama.cpp-style models",
        "managed_by_helper": "partial",
        "gui_required": False,
        "protocol": "openai_compatible",
        "model_sources": ["huggingface_gguf", "local_file"],
        "good_for": ["OpenAI-compatible local service", "mixed backend experiments"],
        "install_hint": "Install/run LocalAI from its container or native release",
    },
    "faster_whisper": {
        "description": "Speech-to-text runtime/library for speech-to-text models, optimized for local CPU/GPU transcription",
        "managed_by_helper": "planned",
        "gui_required": False,
        "protocol": "python_library",
        "model_sources": ["huggingface", "local_file"],
        "good_for": ["speech to text", "local transcription", "batch audio jobs"],
        "install_hint": "python -m pip install faster-whisper",
    },
    "diffusers": {
        "description": "Hugging Face Diffusers Python library for image/video/audio generation pipelines",
        "managed_by_helper": "planned",
        "gui_required": False,
        "protocol": "python_library",
        "model_sources": ["huggingface", "local_file"],
        "good_for": ["image generation", "video generation experiments", "pipeline prototyping"],
        "install_hint": "python -m pip install diffusers transformers accelerate torch",
    },
    "comfyui": {
        "description": "Node-based image/video generation runtime with a web UI and local API",
        "managed_by_helper": "planned",
        "gui_required": True,
        "protocol": "local_api",
        "model_sources": ["huggingface", "local_file"],
        "good_for": ["image workflows", "video workflows", "visual generation pipelines"],
        "install_hint": "Install ComfyUI, place checkpoints under its models directory, and start its server",
    },
    "lmstudio": {
        "description": "Desktop model catalog and OpenAI-compatible local server",
        "managed_by_helper": False,
        "gui_required": True,
        "protocol": "openai_compatible",
        "model_sources": ["huggingface_gguf", "lmstudio_catalog"],
        "good_for": ["desktop local use", "manual model selection"],
        "install_hint": "Install LM Studio and start the local server from the GUI",
    },
}


SOURCE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "ollama": {
        "description": "Ollama model library and local pull store",
        "typical_runtimes": ["ollama"],
    },
    "huggingface": {
        "description": "Hugging Face Hub model repos with tokenizer/config/weights",
        "typical_runtimes": ["vllm", "tgi", "transformers"],
    },
    "huggingface_gguf": {
        "description": "GGUF model files hosted on Hugging Face or another file store",
        "typical_runtimes": ["llamacpp", "localai", "ollama"],
    },
    "local_file": {
        "description": "Local model path, usually GGUF, ONNX, checkpoint, or runtime-specific files",
        "typical_runtimes": ["llamacpp", "localai", "faster_whisper", "diffusers", "comfyui"],
    },
    "azure_speech": {
        "description": "Azure AI Speech voice deployments and voice names",
        "typical_runtimes": ["azure_speech"],
        "online_adapter": "profile_catalog",
    },
    "elevenlabs": {
        "description": "ElevenLabs hosted text-to-speech voices and voice models",
        "typical_runtimes": ["elevenlabs"],
        "online_adapter": "elevenlabs",
    },
    "openai": {
        "description": "OpenAI hosted model catalog and deployments",
        "typical_runtimes": ["openai"],
        "online_adapter": "profile_catalog",
    },
    "anthropic": {
        "description": "Anthropic hosted model catalog",
        "typical_runtimes": ["anthropic"],
        "online_adapter": "profile_catalog",
    },
    "azure_openai": {
        "description": "Azure OpenAI deployments in a configured Azure OpenAI resource",
        "typical_runtimes": ["azure_openai"],
        "online_adapter": "azure_openai",
    },
    "ollama_cloud": {
        "description": "Ollama Cloud hosted catalog and endpoints",
        "typical_runtimes": ["ollama_cloud"],
        "online_adapter": "profile_catalog",
    },
}


class RuntimeCatalog:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.models_config = profile.models or {}
        self.generated_models_config = self._load_generated_models_config()

    def list(self, include_gui: bool = False) -> list[dict[str, Any]]:
        rows = []
        providers = self._providers()
        for name, runtime in RUNTIME_DEFINITIONS.items():
            if runtime.get("gui_required") and not include_gui:
                continue
            provider = providers.get(name, {})
            rows.append({
                "name": name,
                "description": runtime["description"],
                "gui_required": bool(runtime.get("gui_required", False)),
                "managed_by_helper": runtime.get("managed_by_helper", False),
                "configured": name in providers,
                "enabled": bool(provider.get("enabled", True)) if provider else False,
                "endpoint": provider.get("endpoint"),
                "protocol": runtime.get("protocol"),
                "model_sources": runtime.get("model_sources", []),
                "good_for": runtime.get("good_for", []),
                "install_hint": runtime.get("install_hint"),
            })
        return sorted(rows, key=lambda row: row["name"])

    def sources(self) -> list[dict[str, Any]]:
        return [{"name": name, **value} for name, value in sorted(SOURCE_DEFINITIONS.items())]


    def prerequisites(self, runtime: str) -> dict[str, Any]:
        if runtime == "all":
            rows = [self.prerequisites(row["name"]) for row in self.list(include_gui=True)]
            return {
                "name": "runtime_prerequisites",
                "runtime": "all",
                "ok": all(bool(row.get("ok")) for row in rows if row.get("supported_by_aiplane_helper")),
                "runtimes": rows,
            }
        definition = RUNTIME_DEFINITIONS.get(runtime)
        if not definition:
            return {
                "name": "runtime_prerequisites",
                "runtime": runtime,
                "known_runtime": False,
                "supported_by_aiplane_helper": False,
                "ok": False,
                "missing_required": [],
                "missing_optional": [],
                "notes": ["Unknown runtime. Use `aiplane runtimes list --include-gui` to inspect known runtimes."],
            }
        required, optional, packages, notes = _runtime_prerequisite_spec(runtime)
        missing_required = [_tool_row(name, packages.get(name)) for name in required if shutil.which(name) is None]
        missing_optional = [_tool_row(name, packages.get(name)) for name in optional if shutil.which(name) is None]
        managed = definition.get("managed_by_helper")
        install_supported = runtime in {"ollama", "vllm", "tgi", "transformers", "localai"}
        return {
            "name": "runtime_prerequisites",
            "runtime": runtime,
            "known_runtime": True,
            "supported_by_aiplane_helper": runtime in {"ollama", "vllm", "tgi", "transformers", "localai", "lmstudio", "llamacpp"},
            "helper_management": managed,
            "install_supported_by_helper": install_supported,
            "os": _os_summary(),
            "ok": not missing_required,
            "required_tools": [_tool_row(name, packages.get(name), installed=shutil.which(name) is not None) for name in required],
            "optional_tools": [_tool_row(name, packages.get(name), installed=shutil.which(name) is not None) for name in optional],
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "ubuntu_install_hint": _ubuntu_install_hint(missing_required + missing_optional),
            "runtime_install_hint": definition.get("install_hint"),
            "notes": notes,
        }

    def map(self, include_gui: bool = False) -> dict[str, Any]:
        return {
            "diagram": _diagram(include_gui=include_gui),
            "sources": self.sources(),
            "runtimes": self.list(include_gui=include_gui),
            "notes": [
                "A catalog/source supplies model files or model identifiers.",
                "A runtime loads those files into CPU/GPU memory and serves inference.",
                "GUI-required runtimes are omitted by default from managed runtime commands.",
            ],
        }

    def models_by_runtime(self, runtime: str | None = None, include_gui: bool = False) -> dict[str, Any]:
        rows: dict[str, list[dict[str, Any]]] = {}
        for model_name, model in self._models().items():
            for runtime_name in self.supported_runtimes(model_name, include_gui=include_gui):
                if runtime and runtime_name != runtime:
                    continue
                rows.setdefault(runtime_name, []).append(self._model_row(model_name, model))
        if runtime and runtime not in rows:
            rows[runtime] = []
        return {"runtime": runtime, "models": {key: sorted(value, key=lambda row: row["name"]) for key, value in sorted(rows.items())}}

    def runtimes_by_model(self, model_name: str, include_gui: bool = False) -> dict[str, Any]:
        model = self._model(model_name)
        preferred = str(model.get("preferred_runtime") or model.get("provider") or "")
        runtimes = []
        for runtime_name in self.supported_runtimes(model_name, include_gui=include_gui):
            runtimes.append({
                "name": runtime_name,
                "preferred": runtime_name == preferred,
                "available": self.runtime_available(runtime_name)["available"],
                "status": self.runtime_available(runtime_name),
                "runtime": RUNTIME_DEFINITIONS.get(runtime_name, {}),
            })
        return {"name": model_name, "model": model.get("model"), "source": self.source_for_model(model), "preferred_runtime": preferred or None, "runtimes": runtimes}

    def supported_runtimes(self, model_name: str, include_gui: bool = False) -> list[str]:
        return self.compatible_runtimes_for_entry(self._model(model_name), include_gui=include_gui)

    def compatible_runtimes_for_entry(self, model: dict[str, Any], include_gui: bool = False) -> list[str]:
        provider = self._providers().get(str(model.get("provider") or ""), {})
        ownership = str(model.get("ownership") or provider.get("ownership") or "")
        if ownership == "managed_service":
            return []
        configured = model.get("supported_runtimes")
        if isinstance(configured, list) and configured:
            runtimes = [str(value) for value in configured]
        else:
            runtimes = self._infer_runtimes(model)
        preferred = str(model.get("preferred_runtime") or "")
        if preferred:
            runtimes = [preferred, *runtimes]
        if not include_gui:
            runtimes = [name for name in runtimes if not RUNTIME_DEFINITIONS.get(name, {}).get("gui_required")]
        return [name for name in dict.fromkeys(runtimes) if name in RUNTIME_DEFINITIONS]

    def select_runtime(self, model_name: str) -> dict[str, Any]:
        model = self._model(model_name)
        supported = self.supported_runtimes(model_name)
        preferred = str(model.get("preferred_runtime") or model.get("provider") or "")
        ordered = ([preferred] if preferred in supported else []) + [name for name in supported if name != preferred]
        statuses = [self.runtime_available(name) for name in ordered]
        for status in statuses:
            if status["available"]:
                return {"selected": status["name"], "available": True, "statuses": statuses, "supported_runtimes": supported}
        return {"selected": ordered[0] if ordered else None, "available": False, "statuses": statuses, "supported_runtimes": supported}

    def set_preferred_runtime(self, model_name: str, runtime: str) -> dict[str, Any]:
        model = self._model(model_name)
        supported = self.supported_runtimes(model_name, include_gui=True)
        if runtime not in supported:
            raise ValueError(f"runtime {runtime!r} is not supported by model {model_name!r}; supported: {', '.join(supported) or 'none'}")
        model["preferred_runtime"] = runtime
        path = self.profile.root / "models.yaml"
        path.write_text(dump_yaml(self.models_config), encoding="utf-8")
        return {"name": model_name, "preferred_runtime": runtime, "path": str(path)}


    def bundle_plan(self, runtime: str, model_name: str, mode: str = "docker") -> dict[str, Any]:
        if runtime not in RUNTIME_DEFINITIONS:
            raise ValueError(f"unknown runtime: {runtime}")
        if mode not in {"docker", "conda"}:
            raise ValueError("mode must be docker or conda")
        model = self._model(model_name)
        model_id = str(model.get("model") or model_name)
        files = {
            "Dockerfile": _dockerfile_for_runtime(runtime, model_id),
            "environment.yaml": _conda_yaml_for_runtime(runtime),
        }
        selected_file = "Dockerfile" if mode == "docker" else "environment.yaml"
        return {
            "name": f"{runtime}-{model_name}-{mode}",
            "runtime": runtime,
            "model": model_name,
            "model_id": model_id,
            "mode": mode,
            "selected_file": selected_file,
            "files": files,
            "commands": _bundle_commands(runtime, model_name, mode, selected_file),
            "notes": [
                "This is a render-only reproducibility plan; it does not build images, create environments, or pull model weights.",
                "Runtime-specific tuning such as tensor parallelism, quantization, GPU devices, and mounted model caches should be added before production use.",
            ],
        }

    def runtime_available(self, runtime: str) -> dict[str, Any]:
        providers = self._providers()
        provider = providers.get(runtime, {})
        definition = RUNTIME_DEFINITIONS.get(runtime, {})
        if runtime == "ollama":
            endpoint = str(provider.get("endpoint", "http://localhost:11434"))
            reachable, reason = OllamaBackend(endpoint, int(provider.get("timeout_seconds", 5))).is_reachable()
            payload = {"name": runtime, "available": reachable, "reason": reason, "endpoint": endpoint}
            return payload if reachable else {**payload, "suggested_actions": _runtime_suggestions(runtime, "start")}
        if definition.get("protocol") == "openai_compatible":
            endpoint = str(provider.get("endpoint", "")).rstrip("/")
            if not endpoint:
                return {"name": runtime, "available": False, "reason": "endpoint is not configured", "endpoint": None, "suggested_actions": _runtime_suggestions(runtime, "configure")}
            if not bool(provider.get("enabled", True)):
                return {"name": runtime, "available": False, "reason": "provider is disabled", "endpoint": endpoint, "suggested_actions": _runtime_suggestions(runtime, "configure")}
            reachable, reason = OpenAICompatibleBackend(endpoint, int(provider.get("timeout_seconds", 5))).is_reachable()
            payload = {"name": runtime, "available": reachable, "reason": reason, "endpoint": endpoint}
            return payload if reachable else {**payload, "suggested_actions": _runtime_suggestions(runtime, "start")}
        if definition.get("protocol") == "azure_speech":
            provider = providers.get(runtime, {})
            key_env = str(provider.get("api_key_env") or "AZURE_SPEECH_KEY")
            region_env = str(provider.get("region_env") or "AZURE_SPEECH_REGION")
            enabled = bool(provider.get("enabled", True))
            key_present = bool(os.environ.get(key_env) or provider.get("credential_ref"))
            region_present = bool(os.environ.get(region_env) or provider.get("region"))
            available = enabled and key_present and region_present
            missing = []
            if not enabled:
                missing.append("provider is disabled")
            if not key_present:
                missing.append(f"missing env var {key_env}")
            if not region_present:
                missing.append(f"missing env var {region_env}")
            return {"name": runtime, "available": available, "reason": "configured" if available else "; ".join(missing), "endpoint": provider.get("endpoint"), "suggested_actions": _runtime_suggestions(runtime, "configure")}
        if runtime in {"transformers", "faster_whisper", "diffusers"}:
            package = "faster_whisper" if runtime == "faster_whisper" else runtime
            installed = importlib.util.find_spec(package) is not None
            payload = {
                "name": runtime,
                "available": False,
                "installed": installed,
                "reason": f"{runtime} is installed, but it is a library path rather than a running inference endpoint" if installed else f"{runtime} is not installed; install it for script-based use",
                "endpoint": None,
            }
            return {**payload, "suggested_actions": _runtime_suggestions(runtime, "install" if not installed else "library")}
        return {"name": runtime, "available": False, "reason": "runtime availability check is not wired", "endpoint": provider.get("endpoint"), "suggested_actions": _runtime_suggestions(runtime, "manual")}

    def source_for_model(self, model: dict[str, Any]) -> str:
        if model.get("source"):
            return str(model.get("source"))
        provider = str(model.get("provider", ""))
        model_id = str(model.get("model", ""))
        if provider == "ollama":
            return "ollama"
        if provider in {"vllm", "tgi", "transformers"} or "/" in model_id:
            return "huggingface"
        if provider in {"llamacpp", "localai"} or model_id.endswith(".gguf"):
            return "huggingface_gguf"
        return provider or "unknown"

    def _infer_runtimes(self, model: dict[str, Any]) -> list[str]:
        provider = str(model.get("provider", ""))
        source = self.source_for_model(model)
        runtimes = []
        if provider in RUNTIME_DEFINITIONS:
            runtimes.append(provider)
        runtimes.extend(SOURCE_DEFINITIONS.get(source, {}).get("typical_runtimes", []))
        return runtimes

    def _model_row(self, name: str, model: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "model": model.get("model"),
            "provider": model.get("provider"),
            "preferred_runtime": model.get("preferred_runtime") or model.get("provider"),
            "source": self.source_for_model(model),
            "enabled": bool(model.get("enabled", True)),
            "roles": model.get("roles", []),
        }

    def _providers(self) -> dict[str, dict[str, Any]]:
        providers = self.models_config.get("providers", {})
        return providers if isinstance(providers, dict) else {}

    def _models(self) -> dict[str, dict[str, Any]]:
        generated = self.generated_models_config.get("models", {})
        generated_models = generated if isinstance(generated, dict) else {}
        models = self.models_config.get("models", {})
        curated_models = models if isinstance(models, dict) else {}
        return {**generated_models, **curated_models}

    def _load_generated_models_config(self) -> dict[str, Any]:
        path = self.profile.root / "models.generated.yaml"
        if not path.exists():
            return {}
        data = parse_yaml(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _model(self, name: str) -> dict[str, Any]:
        models = self._models()
        model = models.get(name)
        if not isinstance(model, dict):
            raise ValueError(f"unknown model: {name}")
        return model


def _dockerfile_for_runtime(runtime: str, model_id: str) -> str:
    if runtime == "ollama":
        return (
            "FROM ollama/ollama:latest\n"
            "EXPOSE 11434\n"
            f"# Pull after the service starts, or bake a derived image with: ollama pull {model_id}\n"
        )
    if runtime == "vllm":
        return (
            "FROM python:3.13-slim\n"
            "RUN python -m pip install --no-cache-dir --upgrade pip vllm\n"
            "EXPOSE 8000\n"
            f"CMD [\"python\", \"-m\", \"vllm.entrypoints.openai.api_server\", \"--host\", \"0.0.0.0\", \"--model\", \"{model_id}\"]\n"
        )
    if runtime == "tgi":
        return (
            "FROM ghcr.io/huggingface/text-generation-inference:latest\n"
            f"ENV MODEL_ID={model_id}\n"
            "EXPOSE 80\n"
        )
    if runtime == "localai":
        return (
            "FROM localai/localai:latest\n"
            "EXPOSE 8080\n"
            f"# Mount or copy the model assets for {model_id} into the LocalAI models directory.\n"
        )
    if runtime == "llamacpp":
        return (
            "FROM ubuntu:24.04\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*\n"
            "EXPOSE 8080\n"
            f"# Add llama-server installation and mount the GGUF file for {model_id}.\n"
        )
    packages = " ".join(_pip_packages_for_runtime(runtime))
    return (
        "FROM python:3.13-slim\n"
        f"RUN python -m pip install --no-cache-dir --upgrade pip {packages}\n"
        f"# Add your entrypoint for {runtime} and model {model_id}.\n"
    )


def _conda_yaml_for_runtime(runtime: str) -> str:
    packages = _pip_packages_for_runtime(runtime)
    lines = [
        f"name: aiplane-{runtime}",
        "channels:",
        "  - conda-forge",
        "dependencies:",
        "  - python=3.13",
        "  - pip",
    ]
    if packages:
        lines.append("  - pip:")
        lines.extend(f"      - {package}" for package in packages)
    else:
        lines.append("  # This runtime is usually installed as a native binary or container rather than Python packages.")
    return "\n".join(lines) + "\n"


def _pip_packages_for_runtime(runtime: str) -> list[str]:
    packages = {
        "vllm": ["vllm"],
        "transformers": ["torch", "transformers", "accelerate", "huggingface_hub"],
        "faster_whisper": ["faster-whisper"],
        "diffusers": ["torch", "transformers", "accelerate", "diffusers"],
        "localai": [],
        "llamacpp": [],
        "ollama": [],
        "tgi": [],
        "comfyui": [],
        "lmstudio": [],
    }
    return packages.get(runtime, [])


def _bundle_commands(runtime: str, model_name: str, mode: str, selected_file: str) -> list[str]:
    if mode == "docker":
        tag = f"aiplane-{runtime}-{model_name}:local"
        return [
            f"docker build -t {tag} -f {selected_file} .",
            f"docker run --rm -p 8000:8000 {tag}",
        ]
    return [
        f"conda env create -f {selected_file}",
        f"conda activate aiplane-{runtime}",
    ]


def _diagram(include_gui: bool = False) -> str:
    lines = ["flowchart LR"]
    lines.extend([
        '  HF["Hugging Face Hub"] --> VLLM["vLLM"]',
        '  HF --> TGI["TGI"]',
        '  HF --> TR["Transformers"]',
        '  HFGGUF["HF GGUF / local GGUF"] --> LLAMACPP["llama.cpp"]',
        '  HFGGUF --> LOCALAI["LocalAI"]',
        '  HFGGUF --> OLLAMA["Ollama import"]',
        '  OLLAMACAT["Ollama library"] --> OLLAMA',
        '  VLLM --> OPENAI["OpenAI-compatible /v1"]',
        '  TGI --> OPENAI',
        '  LLAMACPP --> OPENAI',
        '  LOCALAI --> OPENAI',
        '  OLLAMA --> OAI2["Ollama /v1 + native API"]',
        '  OPENAI --> IDE["Continue / Cursor-style clients / aiplane"]',
        '  OAI2 --> IDE',
        '  HF --> FW["faster-whisper"]',
        '  AZSPEECH["Azure AI Speech"] --> AZTTS["Managed TTS"]',
        '  HF --> DIFF["Diffusers"]',
    ])
    if include_gui:
        lines.extend([
            '  HFGGUF --> LMS["LM Studio GUI"]',
            '  LMS --> OPENAI',
        ])
    return "\n".join(lines)


def _os_summary() -> dict[str, Any]:
    os_release: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            os_release[key] = value.strip().strip('"')
    except OSError:
        pass
    ids = " ".join(filter(None, [os_release.get("ID", ""), os_release.get("ID_LIKE", "")]))
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "id": os_release.get("ID"),
        "id_like": os_release.get("ID_LIKE"),
        "pretty_name": os_release.get("PRETTY_NAME"),
        "ubuntu_like": "ubuntu" in ids or "debian" in ids,
    }


def _tool_row(name: str, ubuntu_package: str | None = None, installed: bool | None = None) -> dict[str, Any]:
    path = shutil.which(name)
    return {
        "name": name,
        "installed": bool(path) if installed is None else bool(installed),
        "path": path,
        "ubuntu_package": ubuntu_package or name,
    }


def _ubuntu_install_hint(rows: list[dict[str, Any]]) -> str | None:
    packages = sorted({str(row.get("ubuntu_package") or row.get("name")) for row in rows if row.get("ubuntu_package")})
    if not packages:
        return None
    return "sudo apt-get update && sudo apt-get install -y " + " ".join(packages)


def _runtime_prerequisite_spec(runtime: str) -> tuple[list[str], list[str], dict[str, str], list[str]]:
    packages = {
        "curl": "curl",
        "sh": "dash",
        "python": "python3",
        "pip": "python3-pip",
        "docker": "docker.io",
        "llama-server": "llama.cpp",
        "nvidia-smi": "nvidia-utils-535",
    }
    if runtime == "ollama":
        return ["curl", "sh"], [], packages, ["The helper delegates install/update to Ollama's official Linux install script."]
    if runtime == "vllm":
        return ["python", "pip"], ["nvidia-smi"], packages, ["The helper installs vLLM with pip. GPU/CUDA compatibility is still a runtime-native concern."]
    if runtime == "transformers":
        return ["python", "pip"], ["nvidia-smi"], packages, ["Transformers is a Python library path, not a serving endpoint by default."]
    if runtime in {"tgi", "localai"}:
        return ["docker"], ["nvidia-smi"], packages, ["The helper uses Docker images. GPU serving also needs a working NVIDIA container runtime when GPUs are required."]
    if runtime == "llamacpp":
        return ["llama-server"], ["curl"], packages, ["Install/build llama.cpp for your CPU/GPU target and put llama-server on PATH."]
    if runtime == "azure_speech":
        return [], [], packages, ["Azure AI Speech is a managed service; configure AZURE_SPEECH_KEY and AZURE_SPEECH_REGION or a profile credential reference instead of installing a local runtime."]
    if runtime == "lmstudio":
        return [], [], packages, ["LM Studio is GUI-managed. Install it manually and enable the local server from the app."]
    return [], [], packages, ["No automated prerequisite policy is defined for this runtime yet."]


def _runtime_suggestions(runtime: str, situation: str) -> list[str]:
    suggestions = [f"aiplane runtimes prerequisites {runtime}"]
    if runtime in {"ollama", "vllm", "tgi", "transformers", "localai"}:
        suggestions.append(f"aiplane runtimes install {runtime} --dry-run")
    if situation in {"start", "configure"} and runtime in {"ollama", "vllm", "tgi", "localai", "llamacpp"}:
        suggestions.append(f"aiplane runtimes start {runtime} --dry-run")
    if situation == "configure":
        suggestions.append(f"aiplane runtimes configure {runtime} --dry-run")
    if situation == "manual" or runtime in {"lmstudio", "llamacpp"}:
        hint = RUNTIME_DEFINITIONS.get(runtime, {}).get("install_hint")
        if hint:
            suggestions.append(str(hint))
    return suggestions
