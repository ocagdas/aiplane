"""Authoritative contracts for the primary local model runners."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeSpec:
    name: str
    port: int
    endpoint_path: str
    protocol: str
    substrate: str
    health_path: str
    cache_target: str | None
    bundle_modes: tuple[str, ...]
    default_bundle_mode: str
    container_port: int | None = None

    def endpoint(self, host: str = "localhost", port: int | None = None) -> str:
        selected_port = self.port if port is None else port
        return f"http://{host}:{selected_port}{self.endpoint_path}"


PRIMARY_RUNTIME_SPECS = {
    "ollama": RuntimeSpec(
        "ollama", 11434, "", "ollama_api", "native", "/api/tags", "/root/.ollama", ("docker", "native"), "docker", 11434
    ),
    "llamacpp": RuntimeSpec(
        "llamacpp", 8080, "/v1", "openai_compatible", "native", "/health", "/models", ("native",), "native"
    ),
    "mlx": RuntimeSpec(
        "mlx", 8080, "/v1", "openai_compatible", "venv", "/v1/models", None, ("conda", "native"), "conda"
    ),
    "docker_model_runner": RuntimeSpec(
        "docker_model_runner",
        12434,
        "/engines/v1",
        "openai_compatible",
        "docker",
        "/engines/v1/models",
        None,
        ("native",),
        "native",
    ),
    "lmstudio": RuntimeSpec(
        "lmstudio", 1234, "/v1", "openai_compatible", "native", "/v1/models", None, ("native",), "native"
    ),
    "vllm": RuntimeSpec(
        "vllm",
        8000,
        "/v1",
        "openai_compatible",
        "docker",
        "/health",
        "/root/.cache/huggingface",
        ("docker", "conda", "native"),
        "docker",
        8000,
    ),
}


def runtime_spec(name: str) -> RuntimeSpec:
    try:
        return PRIMARY_RUNTIME_SPECS[name]
    except KeyError as exc:
        raise ValueError(f"runtime specification is unavailable for: {name}") from exc


def runtime_endpoint(name: str, host: str = "localhost", port: int | None = None) -> str:
    return runtime_spec(name).endpoint(host, port)
