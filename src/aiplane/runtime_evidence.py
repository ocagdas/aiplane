"""Versioned, render-only model artifact and runtime launch evidence."""

from __future__ import annotations

from typing import Any

from .runtime_definitions import RUNTIME_DEFINITIONS
from .runtime_specs import PRIMARY_RUNTIME_SPECS, runtime_endpoint, runtime_spec

CONTRACT_VERSION = "1.0"
LAUNCH_RENDERERS = set(PRIMARY_RUNTIME_SPECS)


def artifact_lock(model_name: str, model: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model.get("model") or model_name)
    source = str(model.get("source") or model.get("provider") or "")
    immutable_revision = bool(model.get("revision") or model.get("commit_sha"))
    checksum_locked = bool(model.get("checksum") or model.get("sha256") or model.get("digest"))
    complete = immutable_revision and checksum_locked
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": "model_artifact_lock",
        "model_alias": model_name,
        "identity": {
            "source": source or None,
            "model_id": model_id,
            "revision": model.get("revision") or model.get("commit_sha"),
            "file": model.get("file") or model.get("path"),
            "format": model.get("format") or _infer_format(model_id),
            "quantization": model.get("quantization"),
        },
        "integrity": {
            "checksum": model.get("checksum") or model.get("sha256") or model.get("digest"),
            "size_bytes": model.get("size_bytes"),
            "size": model.get("size"),
        },
        "access": {
            "license": model.get("license"),
            "gated": model.get("gated"),
        },
        "runtime_compatibility": {
            "supported": list(model.get("supported_runtimes") or []),
            "preferred": model.get("preferred_runtime"),
        },
        "provenance": {
            "catalog_source": model.get("catalog_source") or model.get("discovered_from") or source or None,
            "discovered_name": model.get("discovered_name"),
            "generated": bool(model.get("_generated") or model.get("generated")),
        },
        "complete": complete,
        "reproducibility": {
            "level": "digest_locked" if complete else "unresolved",
            "immutable_revision": immutable_revision,
            "checksum_locked": checksum_locked,
        },
        "notes": [
            "Null fields are unresolved; they are not inferred or silently pinned.",
            "A complete lock requires both an immutable revision and checksum/digest.",
        ],
    }


def launch_manifest(
    runtime: str,
    model_name: str,
    model: dict[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    context_tokens: int | None = None,
    gpu_devices: list[str] | None = None,
    tensor_parallel: int | None = None,
    offload: str | None = None,
) -> dict[str, Any]:
    if runtime not in RUNTIME_DEFINITIONS:
        raise ValueError(f"unknown runtime: {runtime}")
    if runtime not in LAUNCH_RENDERERS:
        raise ValueError(
            f"runtime {runtime!r} does not have a launch-manifest renderer; supported: {', '.join(sorted(LAUNCH_RENDERERS))}"
        )
    if not host or any(character.isspace() for character in host):
        raise ValueError("launch host must be a non-empty host name or address")
    selected_port = int(port or _default_port(runtime))
    if not 1 <= selected_port <= 65535:
        raise ValueError("launch port must be between 1 and 65535")
    selected_context = int(context_tokens or model.get("context_window_tokens") or 0) or None
    if selected_context is not None and selected_context < 1:
        raise ValueError("context tokens must be positive")
    if tensor_parallel is not None and tensor_parallel < 1:
        raise ValueError("tensor parallel size must be positive")
    devices = [str(value) for value in (gpu_devices or [])]
    model_id = str(model.get("model") or model_name)
    command = _launch_command(
        runtime,
        model_id,
        host=host,
        port=selected_port,
        context_tokens=selected_context,
        tensor_parallel=tensor_parallel,
        offload=offload,
    )
    spec = runtime_spec(runtime)
    protocol = spec.protocol
    artifact = artifact_lock(model_name, model)
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": "runtime_launch_manifest",
        "mode": "render_only",
        "runtime": {
            "name": runtime,
            "version": None,
            "protocol": protocol,
            "requirements": {"commands": [command[0]], "gpu_devices": devices},
        },
        "artifact": artifact,
        "launch": {
            "command": command,
            "working_directory": None,
            "environment": _environment(runtime, devices),
            "mounts": [],
            "host": host,
            "port": selected_port,
            "context_tokens": selected_context,
            "tensor_parallel": tensor_parallel,
            "offload": offload,
        },
        "endpoint": {
            "base_url": runtime_endpoint(runtime, host, selected_port),
            "health_path": spec.health_path,
            "protocol": protocol,
        },
        "reproducibility": {
            "level": "recipe_deterministic",
            "runtime_version_pinned": False,
            "artifact_level": artifact["reproducibility"]["level"],
        },
        "notes": [
            "This manifest is preview-only and never starts a process or pulls weights.",
            "Environment entries contain device selectors only; credentials and secret values are forbidden.",
            "Review runtime version, artifact lock completeness, cache mounts, and vendor-specific tuning before use.",
        ],
    }


def _launch_command(
    runtime: str,
    model_id: str,
    *,
    host: str,
    port: int,
    context_tokens: int | None,
    tensor_parallel: int | None,
    offload: str | None,
) -> list[str]:
    if runtime == "ollama":
        return ["ollama", "serve"]
    if runtime == "vllm":
        command = [
            "vllm",
            "serve",
            model_id,
            "--host",
            host,
            "--port",
            str(port),
        ]
        if context_tokens:
            command.extend(["--max-model-len", str(context_tokens)])
        if tensor_parallel:
            command.extend(["--tensor-parallel-size", str(tensor_parallel)])
        return command
    if runtime == "mlx":
        return ["python", "-m", "mlx_lm.server", "--model", model_id, "--host", host, "--port", str(port)]
    if runtime == "llamacpp":
        command = ["llama-server", "--model", model_id, "--host", host, "--port", str(port)]
        if context_tokens:
            command.extend(["--ctx-size", str(context_tokens)])
        if offload:
            command.extend(["--n-gpu-layers", offload])
        return command
    if runtime == "docker_model_runner":
        return ["docker", "model", "run", model_id]
    return ["lms", "server", "start", "--port", str(port)]


def _environment(runtime: str, devices: list[str]) -> dict[str, str]:
    if not devices:
        return {}
    if runtime not in {"ollama", "vllm", "llamacpp"}:
        return {}
    return {"CUDA_VISIBLE_DEVICES": ",".join(devices)}


def _default_port(runtime: str) -> int:
    return runtime_spec(runtime).port


def _infer_format(model_id: str) -> str | None:
    lowered = model_id.lower()
    if lowered.endswith(".gguf"):
        return "gguf"
    if lowered.endswith(".safetensors"):
        return "safetensors"
    return None
