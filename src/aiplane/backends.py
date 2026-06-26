from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Mapping


@dataclass(frozen=True)
class BackendResult:
    backend: str
    text: str
    escalated: bool = False


class LocalBackend:
    name = "local"

    def complete(self, task: str) -> BackendResult:
        return BackendResult(self.name, f"local backend handled task: {task}", False)


class MockCloudBackend:
    name = "mock_cloud"

    def complete(self, task: str) -> BackendResult:
        return BackendResult(self.name, f"mock cloud backend handled escalated task: {task}", True)


class OllamaBackend:
    name = "ollama"

    def __init__(self, endpoint: str = "http://localhost:11434", timeout_seconds: int = 60, headers: Mapping[str, str] | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})

    def available_models(self) -> list[str]:
        request = Request(f"{self.endpoint}/api/tags", headers=self.headers)
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]

    def is_reachable(self) -> tuple[bool, str]:
        try:
            self.available_models()
            return True, "Ollama is reachable"
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            return False, f"Ollama is not reachable: {exc}"

    def chat(self, model: str, prompt: str) -> BackendResult:
        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = Request(
            f"{self.endpoint}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            raise RuntimeError(
                f"Ollama is not reachable at {self.endpoint}. Run `ollama serve`, "
                f"then `ollama pull {model}`, or use `--dry-run` to preview prompts. Details: {exc}"
            ) from exc
        message = body.get("message", {})
        return BackendResult(self.name, str(message.get("content", "")), False)


class OpenAICompatibleBackend:
    name = "openai_compatible"

    def __init__(self, endpoint: str, timeout_seconds: int = 60, headers: Mapping[str, str] | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})

    def available_models(self) -> list[str]:
        request = Request(f"{self.endpoint}/models", headers=self.headers)
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = payload.get("data", [])
        return sorted(str(model.get("id")) for model in data if isinstance(model, dict) and model.get("id"))

    def is_reachable(self) -> tuple[bool, str]:
        try:
            self.available_models()
            return True, "OpenAI-compatible endpoint is reachable"
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            return False, f"OpenAI-compatible endpoint is not reachable: {exc}"

    def chat(self, model: str, prompt: str) -> BackendResult:
        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = Request(
            f"{self.endpoint}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            raise RuntimeError(
                f"OpenAI-compatible endpoint is not reachable at {self.endpoint}. "
                f"Start the runtime or configure a reachable local/remote endpoint. Details: {exc}"
            ) from exc
        choices = body.get("choices", [])
        if not choices:
            return BackendResult(self.name, "", False)
        first = choices[0]
        if not isinstance(first, dict):
            return BackendResult(self.name, "", False)
        message = first.get("message")
        if isinstance(message, dict):
            return BackendResult(self.name, str(message.get("content", "")), False)
        return BackendResult(self.name, str(first.get("text", "")), False)
