from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.error import URLError

from .backends import (
    AnthropicMessagesBackend,
    AzureOpenAIBackend,
    BackendResult,
    OllamaBackend,
    OpenAICompatibleBackend,
)
from .model_catalog import (
    ModelStatus,
    _capability_average,
    build_smoke_prompt,
    capability_profile,
    capability_tags,
    model_source,
    ownership_for_model,
    top_capabilities,
)
from .runtime_catalog import RuntimeCatalog
from .runtime_pull import runtime_model_id
from .secrets import CredentialStore


class ModelExecution:
    """Runtime execution, pull planning, and endpoint readiness for model aliases."""

    def __init__(self, catalog: Any):
        self.catalog = catalog
        self.profile = catalog.profile
        self.config = catalog.config
        self.command_runner = catalog.command_runner
        self.http_transport = catalog.http_transport

    def providers(self) -> dict[str, dict[str, Any]]:
        return self.catalog.providers()

    def models(self) -> dict[str, dict[str, Any]]:
        return self.catalog.models()

    def pull_plan(
        self,
        name: str | None = None,
        source: str | None = None,
        model_id: str | None = None,
        for_runtime: str | None = None,
        file: str | None = None,
    ) -> dict[str, Any]:
        if name:
            model = self.get(name)
            source = source or model_source(model)
            model_id = model_id or str(model.get("model") or "")
            for_runtime = for_runtime or str(model.get("preferred_runtime") or model.get("provider") or "")
        if not source or not model_id:
            raise ValueError("pull planning requires a model alias, or both --source and --model-id")
        command: list[str]
        if source == "ollama":
            command = ["ollama", "pull", model_id]
        elif source == "huggingface":
            command = [
                "python",
                "-c",
                f"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')",
            ]
        elif source == "huggingface_gguf":
            if file:
                command = [
                    "python",
                    "-c",
                    f"from huggingface_hub import hf_hub_download; hf_hub_download('{model_id}', filename='{file}')",
                ]
            else:
                command = [
                    "python",
                    "-c",
                    f"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')",
                ]
        elif source == "civitai":
            command = [
                "python",
                "-m",
                "aiplane",
                "providers",
                "models",
                "civitai",
                "--online",
                "--query",
                model_id,
            ]
        elif source == "modelscope":
            command = ["provider-native-pull", "modelscope", model_id]
        elif source == "local_file":
            command = ["test", "-f", model_id]
        else:
            command = ["provider-native-pull", source, model_id]
        return {
            "name": name,
            "source": source,
            "model": model_id,
            "runtime": for_runtime,
            "file": file,
            "command": command,
        }

    def get(self, name: str) -> dict[str, Any]:
        models = self.models()
        if name not in models:
            raise ValueError(f"unknown model: {name}")
        return models[name]

    def show(self, name: str) -> dict[str, Any]:
        model = {"name": name, **dict(self.get(name))}
        provider_name = str(model.get("provider", ""))
        provider = self.providers().get(provider_name, {})
        model["source"] = model_source(model)
        model["ownership"] = ownership_for_model(model, provider)

        supported_runtimes = RuntimeCatalog(self.profile).compatible_runtimes_for_entry(model, include_gui=True)
        runtime_value = (
            None
            if model["ownership"] == "managed_service"
            else (model.get("preferred_runtime") or provider.get("runtime") or provider_name)
        )
        model["runtime"] = runtime_value
        model["runtime_endpoint"] = None if model["ownership"] == "managed_service" else provider_name
        model["supported_runtimes"] = supported_runtimes
        model["provider_config"] = provider
        model["capabilities"] = capability_profile(model)
        model["capability_avg_score"] = _capability_average(model["capabilities"])
        from .benchmarks import latest_benchmark_summary

        model["latest_benchmark"] = latest_benchmark_summary(self.profile, name)
        model["capability_tags"] = capability_tags(model["capabilities"])
        model["top_capabilities"] = top_capabilities(model["capabilities"])
        return model

    def doctor(self) -> list[ModelStatus]:
        statuses = []
        provider_probe_cache: dict[
            tuple[str, str, tuple[tuple[str, str], ...]], tuple[bool, str, list[str] | None]
        ] = {}
        for name, model in self.models().items():
            statuses.append(self._status(name, model, provider_probe_cache))
        return statuses

    def pull(self, name: str) -> str:
        model = self.get(name)
        if model.get("provider") != "ollama":
            raise ValueError("pull is only supported for Ollama models")
        model_id = str(model.get("model"))
        result = self.command_runner.run(
            ["ollama", "pull", model_id],
            cwd=self.profile.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode:
            raise RuntimeError(output or f"ollama pull failed for {model_id}")
        return output

    def complete(
        self,
        name: str,
        prompt: str,
        timeout_seconds: int | None = None,
        purpose: str = "chat",
    ) -> BackendResult:
        model = self.get(name)
        self.require_execution_capability(name, model, purpose)
        provider_name = self._runtime_for_model(name, model)
        if provider_name in {"ollama", "ollama_cloud"}:
            return self._ollama_backend(provider_name, timeout_seconds=timeout_seconds).chat(
                self._execution_model_id(provider_name, model), prompt
            )
        if self._is_openai_compatible(provider_name):
            return self._openai_compatible_backend(provider_name, model, timeout_seconds=timeout_seconds).chat(
                str(model.get("model")), prompt
            )
        if self._is_azure_openai(provider_name):
            return self._azure_openai_backend(provider_name, model, timeout_seconds=timeout_seconds).chat(
                str(model.get("model")), prompt
            )
        if self._is_anthropic(provider_name):
            return self._anthropic_backend(provider_name, model, timeout_seconds=timeout_seconds).chat(
                str(model.get("model")), prompt
            )
        raise ValueError(
            f"execution is not wired for runtime/provider: {provider_name}; "
            "supported protocols are ollama_api, openai_compatible, azure_openai, and anthropic_api"
        )

    def require_execution_capability(self, name: str, model: dict[str, Any], purpose: str) -> None:
        roles = {str(role) for role in model.get("roles", []) or []}
        scores = model.get("capability_scores")
        if not isinstance(scores, dict):
            capabilities = model.get("capabilities")
            if isinstance(capabilities, dict):
                scores = capabilities.get("scores")
        score_names = {key for key, value in (scores or {}).items() if self._positive_score(value)}
        purpose_roles = {
            "chat": {"chat", "generation"},
            "analysis": {"analysis", "chat"},
            "completion": {"completion", "autocomplete", "code", "chat"},
            "write": {"generation", "refactor", "code", "chat"},
        }
        purpose_scores = {
            "chat": {"general_chat", "reasoning", "tool_use"},
            "analysis": {"code_analysis", "reasoning", "general_chat"},
            "completion": {"code_completion", "code_generation", "general_chat"},
            "write": {"code_generation", "debugging_refactor", "general_chat"},
        }
        allowed_roles = purpose_roles.get(purpose, purpose_roles["chat"])
        allowed_scores = purpose_scores.get(purpose, purpose_scores["chat"])
        if roles.intersection(allowed_roles) or score_names.intersection(allowed_scores):
            return
        provider_name = str(model.get("provider") or "unknown")
        model_id = str(model.get("model") or "")
        role_text = ", ".join(sorted(roles)) or "none"
        role_hint = next(iter(sorted(allowed_roles)))
        raise ValueError(
            f"model {name!r} is not suitable for {purpose} execution: roles={role_text}. "
            f"Use `aiplane models list --role {role_hint} --enabled-only` to select a compatible model, "
            "or promote/add a reviewed chat/task-capable alias. "
            f"Provider={provider_name!r}, model={model_id!r}."
        )

    @staticmethod
    def _positive_score(value: Any) -> bool:
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    def _execution_model_id(self, runtime_name: str, model: dict[str, Any]) -> str:
        return runtime_model_id(self.profile, runtime_name, model)

    def _runtime_for_model(self, name: str, model: dict[str, Any]) -> str:
        provider_name = str(model.get("provider") or "")
        provider = self.providers().get(provider_name, {})
        if ownership_for_model(model, provider) == "managed_service":
            runtime_fields = [field for field in ["preferred_runtime", "supported_runtimes"] if model.get(field)]
            if runtime_fields:
                raise ValueError(
                    f"managed-service model {name!r} cannot define local runtime fields: {', '.join(runtime_fields)}"
                )
            return provider_name

        runtime_catalog = RuntimeCatalog(self.profile)
        selection = runtime_catalog.select_runtime(name)
        preferred = str(model.get("preferred_runtime") or model.get("provider") or "")
        if selection["available"] and selection["selected"]:
            return str(selection["selected"])
        supported = ", ".join(selection["supported_runtimes"]) or preferred or "none"
        details = "; ".join(f"{status['name']}: {status['reason']}" for status in selection["statuses"])
        raise RuntimeError(
            f"No supported runtime is running for model {name}. Supported runtimes: {supported}. {details}"
        )

    def _ollama_backend(self, provider_name: str, timeout_seconds: int | None = None) -> OllamaBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = str(
            provider.get(
                "endpoint",
                ("http://localhost:11434" if provider_name == "ollama" else "https://ollama.com"),
            )
        )
        timeout = int(timeout_seconds or provider.get("timeout_seconds", 60))
        headers = {}
        credential_ref = str(provider.get("credential_ref") or "")
        api_key = CredentialStore().api_key(credential_ref) if credential_ref else None
        key_env = provider.get("api_key_env")
        if not api_key and key_env and os.environ.get(str(key_env)):
            api_key = os.environ[str(key_env)]
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        return OllamaBackend(endpoint, timeout, headers, http_transport=self.http_transport)

    def _openai_compatible_backend(
        self,
        provider_name: str,
        model: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> OpenAICompatibleBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = self._openai_compatible_endpoint(provider_name, provider)
        timeout = int(timeout_seconds or provider.get("timeout_seconds", 60))
        headers = {}
        api_key = self._api_key(provider, model)
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        return OpenAICompatibleBackend(endpoint, timeout, headers, http_transport=self.http_transport)

    def _azure_openai_backend(
        self,
        provider_name: str,
        model: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> AzureOpenAIBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = str(provider.get("endpoint") or "")
        if not endpoint:
            raise ValueError(f"provider {provider_name!r} is missing endpoint")
        timeout = int(timeout_seconds or provider.get("timeout_seconds", 60))
        headers = {}
        api_key = self._api_key(provider, model)
        if api_key:
            headers["api-key"] = api_key
        return AzureOpenAIBackend(
            endpoint,
            str(provider.get("api_version") or "2024-02-01"),
            timeout,
            headers,
            http_transport=self.http_transport,
        )

    def _anthropic_backend(
        self,
        provider_name: str,
        model: dict[str, Any] | None = None,
        timeout_seconds: int | None = None,
    ) -> AnthropicMessagesBackend:
        provider = self.providers().get(provider_name, {})
        endpoint = str(provider.get("endpoint") or "https://api.anthropic.com")
        timeout = int(timeout_seconds or provider.get("timeout_seconds", 60))
        headers = {}
        api_key = self._api_key(provider, model)
        if api_key:
            headers["x-api-key"] = api_key
        return AnthropicMessagesBackend(
            endpoint,
            timeout,
            headers,
            str(provider.get("api_version") or "2023-06-01"),
            http_transport=self.http_transport,
        )

    def _api_key(self, provider: dict[str, Any], model: dict[str, Any] | None = None) -> str | None:
        model = model or {}
        credential_ref = str(model.get("credential_ref") or provider.get("credential_ref") or "")
        api_key = CredentialStore().api_key(credential_ref) if credential_ref else None
        key_env = model.get("api_key_env") or provider.get("api_key_env")
        if not api_key and key_env and os.environ.get(str(key_env)):
            api_key = os.environ[str(key_env)]
        return api_key

    def _openai_compatible_endpoint(self, provider_name: str, provider: dict[str, Any] | None = None) -> str:
        provider = provider or self.providers().get(provider_name, {})
        endpoint = str(provider.get("endpoint", ""))
        if not endpoint and provider_name == "openai":
            endpoint = "https://api.openai.com/v1"
        if not endpoint:
            raise ValueError(f"provider {provider_name!r} is missing endpoint")
        return endpoint.rstrip("/")

    def _is_openai_compatible(self, provider_name: str) -> bool:
        provider = self.providers().get(provider_name, {})
        protocol = str(provider.get("protocol", ""))
        return protocol == "openai_compatible" or provider_name in {
            "vllm",
            "lmstudio",
            "llamacpp",
            "tgi",
            "localai",
            "openai",
        }

    def _is_azure_openai(self, provider_name: str) -> bool:
        provider = self.providers().get(provider_name, {})
        return provider_name == "azure_openai" or str(provider.get("protocol") or "") == "azure_openai"

    def _is_anthropic(self, provider_name: str) -> bool:
        provider = self.providers().get(provider_name, {})
        return provider_name == "anthropic" or str(provider.get("protocol") or "") in {
            "anthropic_api",
            "anthropic_messages",
        }

    def test_prompt(self, name: str, task: str, target: Path | None = None, dry_run: bool = False) -> BackendResult:
        model = self.get(name)
        prompt = build_smoke_prompt(task, target)
        if dry_run:
            return BackendResult("dry_run", prompt, False)
        provider_name = str(model.get("provider"))
        if (
            provider_name not in {"ollama", "ollama_cloud"}
            and not self._is_openai_compatible(provider_name)
            and not self._is_azure_openai(provider_name)
            and not self._is_anthropic(provider_name)
        ):
            raise ValueError(
                "model test cannot execute this provider yet; use --dry-run or configure an Ollama, "
                "OpenAI-compatible, Azure OpenAI, or Anthropic Messages endpoint"
            )
        return self.complete(name, prompt)

    def _status(
        self,
        name: str,
        model: dict[str, Any],
        provider_probe_cache: dict[tuple[str, str, tuple[tuple[str, str], ...]], tuple[bool, str, list[str] | None]],
    ) -> ModelStatus:
        provider_name = str(model.get("provider", ""))
        provider = self.providers().get(provider_name, {})
        if not bool(model.get("enabled", True)):
            return ModelStatus(name, provider_name, True, False, "model is disabled")
        if provider_name in {"ollama", "ollama_cloud"}:
            if (
                provider_name == "ollama_cloud"
                and provider.get("api_key_env")
                and not os.environ.get(str(provider.get("api_key_env")))
            ):
                return ModelStatus(
                    name,
                    provider_name,
                    True,
                    False,
                    f"missing env var {provider.get('api_key_env')}",
                )
            backend = self._ollama_backend(provider_name)
            probe_key = self._provider_probe_cache_key(provider_name, backend.endpoint, backend.headers)
            reachable, reason, available = provider_probe_cache.get(probe_key) or self._probe_ollama_backend(backend)
            provider_probe_cache.setdefault(probe_key, (reachable, reason, available))
            if not reachable:
                return ModelStatus(name, provider_name, True, False, reason)
            model_id = str(model.get("model", ""))
            pulled = model_id in (available or [])
            return ModelStatus(
                name,
                provider_name,
                True,
                pulled,
                ("model is pulled" if pulled else f"model is not pulled: ollama pull {model_id}"),
            )
        if self._is_openai_compatible(provider_name):
            credential_problem = self._credential_problem(model, provider)
            if credential_problem:
                return ModelStatus(name, provider_name, True, False, credential_problem)
            if not bool(provider.get("enabled", True)):
                return ModelStatus(name, provider_name, True, False, "provider is disabled")
            backend = self._openai_compatible_backend(provider_name, model)
            probe_key = self._provider_probe_cache_key(provider_name, backend.endpoint, backend.headers)
            reachable, reason, available = provider_probe_cache.get(probe_key) or self._probe_openai_compatible_backend(
                backend
            )
            provider_probe_cache.setdefault(probe_key, (reachable, reason, available))
            if not reachable:
                return ModelStatus(name, provider_name, True, False, reason)
            model_id = str(model.get("model", ""))
            usable = not available or model_id in available
            return ModelStatus(
                name,
                provider_name,
                True,
                usable,
                ("model is available" if usable else f"model was not listed by provider: {model_id}"),
            )
        if self._is_azure_openai(provider_name) or self._is_anthropic(provider_name):
            credential_problem = self._credential_problem(model, provider)
            if credential_problem:
                return ModelStatus(name, provider_name, True, False, credential_problem)
            if not bool(provider.get("enabled", True)):
                return ModelStatus(name, provider_name, True, False, "provider is disabled")
            if self._is_azure_openai(provider_name) and not provider.get("endpoint"):
                return ModelStatus(name, provider_name, True, False, "provider is missing endpoint")
            return ModelStatus(name, provider_name, True, True, "model endpoint is configured")
        credential_ref = str(model.get("credential_ref") or provider.get("credential_ref") or "")
        if credential_ref:
            present = bool(CredentialStore().api_key(credential_ref))
            return ModelStatus(
                name,
                provider_name,
                True,
                present,
                (f"credential {credential_ref} is present" if present else f"missing credential {credential_ref}"),
            )
        key_env = provider.get("api_key_env")
        if key_env:
            present = bool(os.environ.get(str(key_env)))
            return ModelStatus(
                name,
                provider_name,
                True,
                present,
                (f"env var {key_env} is present" if present else f"missing env var {key_env}"),
            )
        return ModelStatus(
            name,
            provider_name,
            bool(provider),
            False,
            "provider has no usable local check yet",
        )

    def _credential_problem(self, model: dict[str, Any], provider: dict[str, Any]) -> str | None:
        credential_ref = str(model.get("credential_ref") or provider.get("credential_ref") or "")
        key_env = model.get("api_key_env") or provider.get("api_key_env")
        if credential_ref and not CredentialStore().api_key(credential_ref):
            return f"missing credential {credential_ref}"
        if not credential_ref and key_env and not os.environ.get(str(key_env)):
            return f"missing env var {key_env}"
        return None

    @staticmethod
    def _provider_probe_cache_key(
        provider_name: str, endpoint: str, headers: dict[str, Any]
    ) -> tuple[str, str, tuple[tuple[str, str], ...]]:
        return (
            provider_name,
            endpoint,
            tuple(sorted((str(key), str(value)) for key, value in headers.items())),
        )

    @staticmethod
    def _probe_ollama_backend(backend: OllamaBackend) -> tuple[bool, str, list[str] | None]:
        try:
            available = backend.available_models()
            return True, "Ollama is reachable", available
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            return False, f"Ollama is not reachable: {exc}", None

    @staticmethod
    def _probe_openai_compatible_backend(
        backend: OpenAICompatibleBackend,
    ) -> tuple[bool, str, list[str] | None]:
        try:
            available = backend.available_models()
            return True, "OpenAI-compatible endpoint is reachable", available
        except (URLError, TimeoutError, OSError, ConnectionError) as exc:
            return False, f"OpenAI-compatible endpoint is not reachable: {exc}", None
