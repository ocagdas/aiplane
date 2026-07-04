from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
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

    def __init__(
        self,
        endpoint: str = "http://localhost:11434",
        timeout_seconds: int = 60,
        headers: Mapping[str, str] | None = None,
    ):
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
            detail = str(exc)
            if isinstance(exc, TimeoutError) or "timed out" in detail.lower():
                raise RuntimeError(
                    f"Ollama request timed out at {self.endpoint} after {self.timeout_seconds}s while running {model!r}. "
                    "The server may still be starting, the model may still be loading, or the model may be too large "
                    "for the current machine/timeout. Run `aiplane runtimes status ollama`, "
                    f"`aiplane runtimes pull ollama --model {model}`, or use `--dry-run` to preview prompts. "
                    f"Details: {exc}"
                ) from exc
            raise RuntimeError(
                f"Ollama endpoint is not reachable at {self.endpoint}. Run `aiplane runtimes start ollama`, "
                f"then `aiplane runtimes pull ollama --model {model}`, or use `--dry-run` to preview prompts. "
                f"Details: {exc}"
            ) from exc
        message = body.get("message", {})
        return BackendResult(self.name, str(message.get("content", "")), False)


class OpenAICompatibleBackend:
    name = "openai_compatible"

    def __init__(
        self,
        endpoint: str,
        timeout_seconds: int = 60,
        headers: Mapping[str, str] | None = None,
    ):
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


class AnthropicMessagesBackend:
    name = "anthropic_messages"

    def __init__(
        self,
        endpoint: str = "https://api.anthropic.com",
        timeout_seconds: int = 60,
        headers: Mapping[str, str] | None = None,
        api_version: str = "2023-06-01",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})
        self.api_version = api_version

    def chat(self, model: str, prompt: str) -> BackendResult:
        payload = {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.api_version,
            **self.headers,
        }
        request = Request(
            f"{self.endpoint}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            raise RuntimeError(
                f"Anthropic Messages endpoint is not reachable at {self.endpoint}. "
                f"Check provider credentials and endpoint configuration. Details: {exc}"
            ) from exc
        chunks = body.get("content", [])
        if isinstance(chunks, list):
            return BackendResult(
                self.name,
                "".join(str(chunk.get("text", "")) for chunk in chunks if isinstance(chunk, dict)),
                True,
            )
        return BackendResult(self.name, str(chunks or ""), True)


class AzureOpenAIBackend:
    name = "azure_openai"

    def __init__(
        self,
        endpoint: str,
        api_version: str = "2024-02-01",
        timeout_seconds: int = 60,
        headers: Mapping[str, str] | None = None,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_version = api_version
        self.timeout_seconds = timeout_seconds
        self.headers = dict(headers or {})

    def chat(self, deployment: str, prompt: str) -> BackendResult:
        payload = {
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        base = self.endpoint[:-7] if self.endpoint.endswith("/openai") else self.endpoint
        query = urlencode({"api-version": self.api_version})
        url = f"{base}/openai/deployments/{deployment}/chat/completions?{query}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            raise RuntimeError(
                f"Azure OpenAI endpoint is not reachable at {self.endpoint}. "
                f"Check the resource endpoint, deployment name, api-version, and credentials. Details: {exc}"
            ) from exc
        choices = body.get("choices", [])
        if not choices or not isinstance(choices[0], dict):
            return BackendResult(self.name, "", True)
        message = choices[0].get("message")
        if isinstance(message, dict):
            return BackendResult(self.name, str(message.get("content", "")), True)
        return BackendResult(self.name, str(choices[0].get("text", "")), True)
