from __future__ import annotations

import importlib.util
import os
import platform
import re
import shlex
import shutil
from pathlib import Path
from typing import Any

from .boundaries import HttpTransport, UrllibHttpTransport
from .backends import OllamaBackend, OpenAICompatibleBackend
from .persistence import atomic_write_text
from .config import dump_yaml, parse_yaml
from .models import Profile
from .runtime_definitions import (
    PROVIDER_ENDPOINT_DEFAULTS,
    RUNTIME_DEFINITIONS,
    SOURCE_DEFINITIONS,
)
from .runtime_evidence import artifact_lock as render_artifact_lock
from .runtime_evidence import launch_manifest as render_launch_manifest
from .runtime_parity import capability_matrix


class RuntimeCatalog:
    def __init__(
        self,
        profile: Profile,
        http_transport: HttpTransport | None = None,
        generated_models_config: dict[str, Any] | None = None,
    ):
        self.profile = profile
        self.http_transport = http_transport or UrllibHttpTransport()
        self.models_config = profile.models or {}
        self.generated_models_config = (
            generated_models_config if generated_models_config is not None else self._load_generated_models_config()
        )

    def list(self, include_gui: bool = False) -> list[dict[str, Any]]:
        rows = []
        providers = self._providers()
        for name, runtime in RUNTIME_DEFINITIONS.items():
            if runtime.get("gui_required") and not include_gui:
                continue
            provider = providers.get(name, {})
            rows.append(
                {
                    "name": name,
                    "description": runtime["description"],
                    "gui_required": bool(runtime.get("gui_required", False)),
                    "managed_by_helper": runtime.get("managed_by_helper", False),
                    "configured": name in self._profile_provider_overrides(),
                    "enabled": (bool(provider.get("enabled", True)) if provider else False),
                    "endpoint": provider.get("endpoint"),
                    "protocol": runtime.get("protocol"),
                    "model_sources": runtime.get("model_sources", []),
                    "good_for": runtime.get("good_for", []),
                    "install_hint": runtime.get("install_hint"),
                }
            )
        return sorted(rows, key=lambda row: row["name"])

    def capabilities(self, runtime: str | None = None) -> dict[str, Any]:
        return capability_matrix(runtime)

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
        install_supported = runtime in {
            "docker_model_runner",
            "ollama",
            "vllm",
            "tgi",
            "transformers",
            "localai",
        }
        return {
            "name": "runtime_prerequisites",
            "runtime": runtime,
            "known_runtime": True,
            "supported_by_aiplane_helper": runtime
            in {
                "docker_model_runner",
                "ollama",
                "vllm",
                "tgi",
                "transformers",
                "localai",
                "lmstudio",
                "llamacpp",
            },
            "helper_management": managed,
            "install_supported_by_helper": install_supported,
            "os": _os_summary(),
            "ok": not missing_required,
            "required_tools": [
                _tool_row(name, packages.get(name), installed=shutil.which(name) is not None) for name in required
            ],
            "optional_tools": [
                _tool_row(name, packages.get(name), installed=shutil.which(name) is not None) for name in optional
            ],
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
        return {
            "runtime": runtime,
            "models": {key: sorted(value, key=lambda row: row["name"]) for key, value in sorted(rows.items())},
        }

    def runtimes_by_model(self, model_name: str, include_gui: bool = False) -> dict[str, Any]:
        model = self._model(model_name)
        preferred = str(model.get("preferred_runtime") or model.get("provider") or "")
        runtimes = []
        for runtime_name in self.supported_runtimes(model_name, include_gui=include_gui):
            runtimes.append(
                {
                    "name": runtime_name,
                    "preferred": runtime_name == preferred,
                    "available": self.runtime_available(runtime_name)["available"],
                    "status": self.runtime_available(runtime_name),
                    "runtime": RUNTIME_DEFINITIONS.get(runtime_name, {}),
                }
            )
        return {
            "name": model_name,
            "model": model.get("model"),
            "source": self.source_for_model(model),
            "preferred_runtime": preferred or None,
            "runtimes": runtimes,
        }

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
                return {
                    "selected": status["name"],
                    "available": True,
                    "statuses": statuses,
                    "supported_runtimes": supported,
                }
        return {
            "selected": ordered[0] if ordered else None,
            "available": False,
            "statuses": statuses,
            "supported_runtimes": supported,
        }

    def set_preferred_runtime(self, model_name: str, runtime: str) -> dict[str, Any]:
        model = self._model(model_name)
        if self._model_ownership(model) == "managed_service":
            raise ValueError(
                f"managed-service model {model_name!r} cannot use a local runtime; configure provider endpoint credentials instead"
            )
        supported = self.supported_runtimes(model_name, include_gui=True)
        if runtime not in supported:
            raise ValueError(
                f"runtime {runtime!r} is not supported by model {model_name!r}; supported: {', '.join(supported) or 'none'}"
            )
        model["preferred_runtime"] = runtime
        path = self.profile.root / "models.yaml"
        atomic_write_text(path, dump_yaml(self.models_config))
        return {"name": model_name, "preferred_runtime": runtime, "path": str(path)}

    def bundle_plan(
        self,
        runtime: str,
        model_name: str,
        mode: str = "docker",
        *,
        cache_volume: str | None = None,
        gpu_devices: list[str] | None = None,
        environment: list[str] | None = None,
        auth_env: str | None = None,
        context_tokens: int | None = None,
        tensor_parallel: int | None = None,
    ) -> dict[str, Any]:
        if runtime not in RUNTIME_DEFINITIONS:
            raise ValueError(f"unknown runtime: {runtime}")
        if mode not in {"docker", "conda"}:
            raise ValueError("mode must be docker or conda")
        model = self._model(model_name)
        if self._model_ownership(model) == "managed_service":
            raise ValueError(
                f"managed-service model {model_name!r} cannot be bundled with runtime {runtime!r}; use provider credentials/endpoints and integration export instead"
            )
        supported = self.compatible_runtimes_for_entry(model, include_gui=True)
        if runtime not in supported:
            raise ValueError(
                f"runtime {runtime!r} is not supported by model {model_name!r}; supported: {', '.join(supported) or 'none'}"
            )
        model_id = str(model.get("model") or model_name)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]*", model_id):
            raise ValueError("bundle model id contains unsupported characters")
        settings = _bundle_settings(
            runtime,
            cache_volume=cache_volume,
            gpu_devices=gpu_devices,
            environment=environment,
            auth_env=auth_env,
            context_tokens=context_tokens,
            tensor_parallel=tensor_parallel,
        )
        files = {
            "Dockerfile": _dockerfile_for_runtime(runtime, model_id),
            "environment.yaml": _conda_yaml_for_runtime(runtime),
        }
        selected_file = "Dockerfile" if mode == "docker" else "environment.yaml"
        return {
            "$schema": "schemas/aiplane-runtime-bundle-v1.schema.json",
            "schema_version": "1.0",
            "record_type": "runtime_bundle",
            "render_only": True,
            "name": f"{runtime}-{model_name}-{mode}",
            "runtime": runtime,
            "model": model_name,
            "model_id": model_id,
            "mode": mode,
            "selected_file": selected_file,
            "files": files,
            "settings": settings,
            "commands": _bundle_commands(runtime, model_name, mode, selected_file, settings),
            "notes": [
                "This is a render-only reproducibility plan; it does not build images, create environments, or pull model weights.",
                "GPU devices, cache volumes, environment references, auth references, context, and tensor parallelism are rendered only when explicitly supplied.",
                "Environment and auth values are never embedded; the generated command references variable names for the operator to populate.",
            ],
        }

    def artifact_lock(self, model_name: str) -> dict[str, Any]:
        model = self._model(model_name)
        if self._model_ownership(model) == "managed_service":
            raise ValueError(f"managed-service model {model_name!r} does not have a local artifact lock")
        lock_model = dict(model)
        lock_model["supported_runtimes"] = self.compatible_runtimes_for_entry(model, include_gui=True)
        return render_artifact_lock(model_name, lock_model)

    def launch_manifest(
        self,
        runtime: str,
        model_name: str,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        context_tokens: int | None = None,
        gpu_devices: list[str] | None = None,
        tensor_parallel: int | None = None,
        offload: str | None = None,
    ) -> dict[str, Any]:
        model = self._model(model_name)
        if self._model_ownership(model) == "managed_service":
            raise ValueError(f"managed-service model {model_name!r} cannot use a local launch manifest")
        supported = self.compatible_runtimes_for_entry(model, include_gui=True)
        if runtime not in supported:
            raise ValueError(
                f"runtime {runtime!r} is not supported by model {model_name!r}; supported: {', '.join(supported) or 'none'}"
            )
        return render_launch_manifest(
            runtime,
            model_name,
            model,
            host=host,
            port=port,
            context_tokens=context_tokens,
            gpu_devices=gpu_devices,
            tensor_parallel=tensor_parallel,
            offload=offload,
        )

    def evidence_bundle(
        self,
        runtime: str,
        model_name: str,
        *,
        host: str = "127.0.0.1",
        port: int | None = None,
        context_tokens: int | None = None,
        gpu_devices: list[str] | None = None,
        tensor_parallel: int | None = None,
        offload: str | None = None,
    ) -> dict[str, Any]:
        """Render the shared artifact and launch contracts used by higher-level workflows."""
        return {
            "contract_version": "1.0",
            "artifact_lock": self.artifact_lock(model_name),
            "launch_manifest": self.launch_manifest(
                runtime,
                model_name,
                host=host,
                port=port,
                context_tokens=context_tokens,
                gpu_devices=gpu_devices,
                tensor_parallel=tensor_parallel,
                offload=offload,
            ),
        }

    def runtime_available(self, runtime: str) -> dict[str, Any]:
        providers = self._providers()
        provider = providers.get(runtime, {})
        definition = RUNTIME_DEFINITIONS.get(runtime, {})
        if runtime == "ollama":
            endpoint = str(provider.get("endpoint", "http://localhost:11434"))
            reachable, reason = OllamaBackend(
                endpoint,
                int(provider.get("timeout_seconds", 5)),
                http_transport=self.http_transport,
            ).is_reachable()
            payload = {
                "name": runtime,
                "available": reachable,
                "reason": reason,
                "endpoint": endpoint,
            }
            return (
                payload
                if reachable
                else {
                    **payload,
                    "suggested_actions": _runtime_suggestions(runtime, "start"),
                }
            )
        if definition.get("protocol") == "openai_compatible":
            endpoint = str(provider.get("endpoint", "")).rstrip("/")
            if not endpoint:
                return {
                    "name": runtime,
                    "available": False,
                    "reason": "endpoint is not configured",
                    "endpoint": None,
                    "suggested_actions": _runtime_suggestions(runtime, "configure"),
                }
            if not bool(provider.get("enabled", True)):
                return {
                    "name": runtime,
                    "available": False,
                    "reason": "provider is disabled",
                    "endpoint": endpoint,
                    "suggested_actions": _runtime_suggestions(runtime, "configure"),
                }
            reachable, reason = OpenAICompatibleBackend(
                endpoint,
                int(provider.get("timeout_seconds", 5)),
                http_transport=self.http_transport,
            ).is_reachable()
            payload = {
                "name": runtime,
                "available": reachable,
                "reason": reason,
                "endpoint": endpoint,
            }
            return (
                payload
                if reachable
                else {
                    **payload,
                    "suggested_actions": _runtime_suggestions(runtime, "start"),
                }
            )
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
            return {
                "name": runtime,
                "available": available,
                "reason": "configured" if available else "; ".join(missing),
                "endpoint": provider.get("endpoint"),
                "suggested_actions": _runtime_suggestions(runtime, "configure"),
            }
        if runtime in {"transformers", "faster_whisper", "diffusers"}:
            package = "faster_whisper" if runtime == "faster_whisper" else runtime
            installed = importlib.util.find_spec(package) is not None
            payload = {
                "name": runtime,
                "available": False,
                "installed": installed,
                "reason": (
                    f"{runtime} is installed, but it is a library path rather than a running inference endpoint"
                    if installed
                    else f"{runtime} is not installed; install it for script-based use"
                ),
                "endpoint": None,
            }
            return {
                **payload,
                "suggested_actions": _runtime_suggestions(runtime, "install" if not installed else "library"),
            }
        return {
            "name": runtime,
            "available": False,
            "reason": "runtime availability check is not wired",
            "endpoint": provider.get("endpoint"),
            "suggested_actions": _runtime_suggestions(runtime, "manual"),
        }

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

    def _profile_provider_overrides(self) -> dict[str, dict[str, Any]]:
        providers = self.models_config.get("providers", {})
        return providers if isinstance(providers, dict) else {}

    def _providers(self) -> dict[str, dict[str, Any]]:
        providers = {name: dict(value) for name, value in PROVIDER_ENDPOINT_DEFAULTS.items()}
        for name, value in self._profile_provider_overrides().items():
            if isinstance(value, dict):
                providers[name] = {
                    **providers.get(name, {}),
                    **value,
                    "origin": "profile",
                }
        return providers

    def _models(self) -> dict[str, dict[str, Any]]:
        generated = self.generated_models_config.get("models", {})
        generated_models = generated if isinstance(generated, dict) else {}
        models = self.models_config.get("models", {})
        curated_models = models if isinstance(models, dict) else {}
        return {**generated_models, **curated_models}

    def _load_generated_models_config(self) -> dict[str, Any]:
        path = self.profile.root / "models.discovered.yaml"
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

    def helper_substrate(self, runtime: str, override: str | None = None) -> str:
        """Resolve the guarded helper substrate used by runtime and stack commands."""
        if override and override not in {"native", "docker"}:
            raise ValueError("runtime substrate must be native or docker")
        if override:
            return override
        provider = self._providers().get(runtime, {})
        return "docker" if str(provider.get("substrate") or "native") == "docker" else "native"

    def _model_ownership(self, model: dict[str, Any]) -> str:
        if model.get("ownership"):
            return str(model.get("ownership"))
        provider = self._providers().get(str(model.get("provider") or ""), {})
        if provider.get("ownership"):
            return str(provider.get("ownership"))
        provider_name = str(model.get("provider") or "")
        return "managed_service" if provider_name in PROVIDER_ENDPOINT_DEFAULTS else "self_managed"


def _dockerfile_for_runtime(runtime: str, model_id: str) -> str:
    if runtime == "ollama":
        return (
            "FROM ollama/ollama:latest\n"
            "EXPOSE 11434\n"
            f"# Pull after the service starts, or bake a derived image with: ollama pull {model_id}\n"
        )
    if runtime == "vllm":
        return (
            "FROM vllm/vllm-openai:latest\n"
            "EXPOSE 8000\n"
            f'ENTRYPOINT ["vllm", "serve", "{model_id}", "--host", "0.0.0.0"]\n'
        )
    if runtime == "tgi":
        return f"FROM ghcr.io/huggingface/text-generation-inference:latest\nENV MODEL_ID={model_id}\nEXPOSE 80\n"
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
        lines.append(
            "  # This runtime is usually installed as a native binary or container rather than Python packages."
        )
    return "\n".join(lines) + "\n"


def _pip_packages_for_runtime(runtime: str) -> list[str]:
    packages = {
        "vllm": ["vllm"],
        "mlx": ["mlx-lm"],
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


_BUNDLE_RUNTIME_PORTS = {"ollama": 11434, "vllm": 8000, "tgi": 80, "localai": 8080, "llamacpp": 8080}
_BUNDLE_CACHE_TARGETS = {
    "ollama": "/root/.ollama",
    "vllm": "/root/.cache/huggingface",
    "tgi": "/data",
    "localai": "/build/models",
    "llamacpp": "/models",
    "transformers": "/root/.cache/huggingface",
}


def _bundle_settings(
    runtime: str,
    *,
    cache_volume: str | None,
    gpu_devices: list[str] | None,
    environment: list[str] | None,
    auth_env: str | None,
    context_tokens: int | None,
    tensor_parallel: int | None,
) -> dict[str, Any]:
    safe_name = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    safe_env = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    devices = [str(value) for value in gpu_devices or [] if value]
    env_names = [str(value) for value in environment or [] if value]
    if cache_volume and not safe_name.fullmatch(cache_volume):
        raise ValueError("cache volume must contain only letters, numbers, dot, underscore, and dash")
    if any(not re.fullmatch(r"[A-Za-z0-9_.:-]+", value) for value in devices):
        raise ValueError("GPU device selectors may only contain letters, numbers, dot, colon, underscore, and dash")
    if any(not safe_env.fullmatch(value) for value in env_names):
        raise ValueError("environment references must be variable names, not KEY=value pairs")
    if auth_env and not safe_env.fullmatch(auth_env):
        raise ValueError("auth environment reference must be a variable name")
    if context_tokens is not None and context_tokens < 1:
        raise ValueError("context tokens must be positive")
    if tensor_parallel is not None and tensor_parallel < 1:
        raise ValueError("tensor parallel size must be positive")
    return {
        "port": _BUNDLE_RUNTIME_PORTS.get(runtime, 8000),
        "cache": {"volume": cache_volume, "target": _BUNDLE_CACHE_TARGETS.get(runtime)} if cache_volume else None,
        "gpu_devices": devices,
        "environment": list(dict.fromkeys(env_names)),
        "auth_env": auth_env,
        "context_tokens": context_tokens,
        "tensor_parallel": tensor_parallel,
    }


def _bundle_commands(
    runtime: str, model_name: str, mode: str, selected_file: str, settings: dict[str, Any]
) -> list[str]:
    if mode == "docker":
        tag = f"aiplane-{runtime}-{model_name}:local"
        port = int(settings["port"])
        run = ["docker", "run", "--rm", "-p", f"{port}:{port}"]
        devices = settings.get("gpu_devices") or []
        if devices:
            run.extend(["--gpus", "all" if devices == ["all"] else f"device={','.join(devices)}"])
        cache = settings.get("cache")
        if cache and cache.get("target"):
            run.extend(["--mount", f"type=volume,src={cache['volume']},dst={cache['target']}"])
        for env_name in settings.get("environment") or []:
            run.extend(["--env", env_name])
        if settings.get("auth_env"):
            run.extend(["--env", str(settings["auth_env"])])
        run.append(tag)
        if runtime == "vllm":
            if settings.get("context_tokens"):
                run.extend(["--max-model-len", str(settings["context_tokens"])])
            if settings.get("tensor_parallel"):
                run.extend(["--tensor-parallel-size", str(settings["tensor_parallel"])])
        return [
            shlex.join(["docker", "build", "-t", tag, "-f", selected_file, "."]),
            shlex.join(run),
        ]
    return [
        f"conda env create -f {selected_file}",
        f"conda activate aiplane-{runtime}",
    ]


def _diagram(include_gui: bool = False) -> str:
    lines = ["flowchart LR"]
    lines.extend(
        [
            '  HF["Hugging Face Hub"] --> VLLM["vLLM"]',
            '  HF --> TGI["TGI"]',
            '  HF --> TR["Transformers"]',
            '  HFGGUF["HF GGUF / local GGUF"] --> LLAMACPP["llama.cpp"]',
            '  HFGGUF --> LOCALAI["LocalAI"]',
            '  HFGGUF --> OLLAMA["Ollama import"]',
            '  OLLAMACAT["Ollama library"] --> OLLAMA',
            '  VLLM --> OPENAI["OpenAI-compatible /v1"]',
            "  TGI --> OPENAI",
            "  LLAMACPP --> OPENAI",
            "  LOCALAI --> OPENAI",
            '  OLLAMA --> OAI2["Ollama /v1 + native API"]',
            '  OPENAI --> IDE["Continue / Cursor-style clients / aiplane"]',
            "  OAI2 --> IDE",
            '  HF --> FW["faster-whisper"]',
            '  AZSPEECH["Azure AI Speech"] --> AZTTS["Managed TTS"]',
            '  HF --> DIFF["Diffusers"]',
        ]
    )
    if include_gui:
        lines.extend(
            [
                '  HFGGUF --> LMS["LM Studio GUI"]',
                "  LMS --> OPENAI",
            ]
        )
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


def _runtime_prerequisite_spec(
    runtime: str,
) -> tuple[list[str], list[str], dict[str, str], list[str]]:
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
        return (
            ["curl", "sh"],
            [],
            packages,
            ["The helper delegates install/update to Ollama's official Linux install script."],
        )
    if runtime == "vllm":
        return (
            ["python", "pip"],
            ["nvidia-smi"],
            packages,
            ["The helper installs vLLM with pip. GPU/CUDA compatibility is still a runtime-native concern."],
        )
    if runtime == "mlx":
        return (
            ["python", "pip"],
            [],
            packages,
            [
                "MLX-LM requires Apple Silicon and macOS; Aiplane renders plans elsewhere but does not claim compatibility."
            ],
        )
    if runtime == "transformers":
        return (
            ["python", "pip"],
            ["nvidia-smi"],
            packages,
            ["Transformers is a Python library path, not a serving endpoint by default."],
        )
    if runtime in {"tgi", "localai"}:
        return (
            ["docker"],
            ["nvidia-smi"],
            packages,
            [
                "The helper uses Docker images. GPU serving also needs a working NVIDIA container runtime when GPUs are required."
            ],
        )
    if runtime == "llamacpp":
        return (
            ["llama-server"],
            ["curl"],
            packages,
            ["Install/build llama.cpp for your CPU/GPU target and put llama-server on PATH."],
        )
    if runtime == "azure_speech":
        return (
            [],
            [],
            packages,
            [
                "Azure AI Speech is a managed service; configure AZURE_SPEECH_KEY and AZURE_SPEECH_REGION or a profile credential reference instead of installing a local runtime."
            ],
        )
    if runtime == "lmstudio":
        return (
            [],
            [],
            packages,
            ["LM Studio is GUI-managed. Install it manually and enable the local server from the app."],
        )
    return (
        [],
        [],
        packages,
        ["No automated prerequisite policy is defined for this runtime yet."],
    )


def _runtime_suggestions(runtime: str, situation: str) -> list[str]:
    suggestions = [f"aiplane runtimes prerequisites {runtime}"]
    if runtime in {"ollama", "vllm", "mlx", "tgi", "transformers", "localai"}:
        suggestions.append(f"aiplane runtimes install {runtime} --dry-run")
    if situation in {"start", "configure"} and runtime in {
        "ollama",
        "vllm",
        "tgi",
        "localai",
        "llamacpp",
    }:
        suggestions.append(f"aiplane runtimes start {runtime} --dry-run")
    if situation == "configure":
        suggestions.append(f"aiplane runtimes configure {runtime} --dry-run")
    if situation == "manual" or runtime in {"lmstudio", "llamacpp"}:
        hint = RUNTIME_DEFINITIONS.get(runtime, {}).get("install_hint")
        if hint:
            suggestions.append(str(hint))
    return suggestions
