"""Normalized capability descriptions for the primary local model runners."""

from __future__ import annotations
from typing import Any

from .runtime_specs import runtime_endpoint

PARITY_RUNTIMES = ("ollama", "llamacpp", "mlx", "docker_model_runner", "lmstudio", "vllm")

_INTERFACES = {
    "ollama": {
        "detection": ("supported", "GET /api/tags"),
        "inventory": ("supported", "ollama list; GET /api/tags"),
        "health": ("supported", "GET /api/tags; ollama ps"),
        "endpoint_export": ("supported", runtime_endpoint("ollama")),
        "lifecycle": ("supported", "guarded helper commands"),
    },
    "llamacpp": {
        "detection": ("supported", "llama-server on PATH; GET /health"),
        "inventory": ("runtime_managed", "GET /models or configured catalog"),
        "health": ("supported", "GET /health"),
        "endpoint_export": ("supported", runtime_endpoint("llamacpp")),
        "lifecycle": ("planned_only", "launch manifest and helper dry-run"),
    },
    "mlx": {
        "detection": ("supported", "python import mlx_lm; GET /v1/models"),
        "inventory": ("runtime_managed", "configured catalog and Hugging Face cache"),
        "health": ("supported", "GET /v1/models"),
        "endpoint_export": ("supported", runtime_endpoint("mlx")),
        "lifecycle": ("planned_only", "launch manifest and pip install plan"),
    },
    "docker_model_runner": {
        "detection": ("supported", "docker model status --json"),
        "inventory": ("supported", "docker model list --format json"),
        "health": ("supported", "docker model status --json; GET /engines/v1/models"),
        "endpoint_export": ("supported", runtime_endpoint("docker_model_runner")),
        "lifecycle": ("supported", "guarded docker model commands"),
    },
    "lmstudio": {
        "detection": ("supported", "lms status; GET /v1/models"),
        "inventory": ("supported", "lms ls --json; lms ps --json"),
        "health": ("supported", "lms status; GET /v1/models"),
        "endpoint_export": ("supported", runtime_endpoint("lmstudio")),
        "lifecycle": ("planned_only", "guarded lms server command plan"),
    },
    "vllm": {
        "detection": ("supported", "python import vllm; GET /health"),
        "inventory": ("runtime_managed", "GET /v1/models"),
        "health": ("supported", "GET /health; GET /metrics"),
        "endpoint_export": ("supported", runtime_endpoint("vllm")),
        "lifecycle": ("supported", "guarded helper commands"),
    },
}

_DETAILS = {
    "identity_mapping": "Catalog alias and runtime-native model id are both preserved.",
    "fit": "Catalog requirements are assessed against discovered RAM, GPU/accelerator memory, and platform data.",
}


def capability_matrix(runtime: str | None = None) -> dict[str, Any]:
    if runtime is not None and runtime not in _INTERFACES:
        raise ValueError("runtime parity contract is available for: " + ", ".join(PARITY_RUNTIMES))
    selected = [runtime] if runtime else list(PARITY_RUNTIMES)
    rows: dict[str, Any] = {}
    for name in selected:
        capabilities = {
            key: {"state": state, "interface": interface} for key, (state, interface) in _INTERFACES[name].items()
        }
        capabilities["identity_mapping"] = {"state": "supported", "detail": _DETAILS["identity_mapping"]}
        capabilities["fit"] = {"state": "supported", "interface": "aiplane hardware assess", "detail": _DETAILS["fit"]}
        rows[name] = capabilities
    return {
        "contract_version": "1.0",
        "runtimes": rows,
        "states": {
            "supported": "Aiplane can inspect or execute through a guarded boundary.",
            "planned_only": "Aiplane renders an exact plan but does not own the external process.",
            "runtime_managed": "The runner exposes its active/cache view; catalog identity remains separate.",
        },
    }
