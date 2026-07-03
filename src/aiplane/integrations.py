from __future__ import annotations

import os
import re
import select
import subprocess
import shutil
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any

from .model_catalog import ModelCatalog, ROLE_CAPABILITY_MAP, expand_capability_filters
from .integration_contracts import (
    MCP_EXPORT_TOOLS,
    ONE_MODEL_TOOLS,
    integration_list,
    required_roles,
)
from .models import Profile
from .output import json_dumps
from .runtime_catalog import RuntimeCatalog
from .runtime_pull import ollama_model_id, runtime_pull_support
from .secrets import CredentialStore


@dataclass(frozen=True)
class IntegrationExport:
    tool: str
    model: str
    provider: str
    endpoint: str
    content: str
    notes: list[str]


class IntegrationManager:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.catalog = ModelCatalog(profile)
        self.credentials = CredentialStore()

    def list(self) -> list[dict[str, str]]:
        return integration_list()

    def roles(self, tool: str) -> dict[str, Any]:
        roles = self._required_roles(tool)
        return {
            "name": "integration_roles",
            "tool": tool,
            "profile": self.profile.name,
            "roles": roles,
            "notes": [
                "Use these roles with aiplane models list --role ROLE --sort-by role to find candidate models.",
                "Continue can use separate chat, autocomplete, and embedding models; most other targets use one primary chat/code model.",
                "MCP targets expose aiplane as a tool server and do not select inference model roles.",
            ],
        }

    def export(
        self,
        tool: str,
        model_name: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        provider: str | None = None,
        runtime: str | None = None,
        capabilities: list[str] | None = None,
        select_best: bool = False,
        chat: str | None = None,
        autocomplete: str | None = None,
        embedding: str | None = None,
    ) -> IntegrationExport:
        if tool in MCP_EXPORT_TOOLS:
            return self._mcp_export(tool)
        if tool == "continue" and not model_name:
            plan = self.plan(
                tool,
                provider=provider,
                runtime=runtime,
                capabilities=capabilities or [],
                select_best=select_best,
                chat=chat,
                autocomplete=autocomplete,
                embedding=embedding,
                endpoint=endpoint,
                api_key_env=api_key_env,
            )
            return self._continue_export_from_plan(plan)
        if (
            tool != "continue"
            and tool not in MCP_EXPORT_TOOLS
            and not model_name
            and (provider or runtime or capabilities or select_best)
        ):
            plan = self.plan(
                tool,
                provider=provider,
                runtime=runtime,
                capabilities=capabilities or [],
                select_best=select_best,
                endpoint=endpoint,
                api_key_env=api_key_env,
            )
            model_name = str(plan["selection"]["primary"]["name"])
        model_name = model_name or self._default_model_name("chat_model", "code_model", "self_managed_model")
        model = self.catalog.get(model_name)
        provider_name = str(model.get("provider"))
        endpoint_value = endpoint or self._endpoint_for_provider(provider_name)
        api_key_value = api_key_env or self._api_key_env_for(model, provider_name)
        if tool == "continue":
            return self._continue_export(model_name, model, provider_name, endpoint_value, api_key_value)
        if tool == "cline":
            return self._cline_export(model_name, model, provider_name, endpoint_value, api_key_value)
        if tool == "zed":
            return self._zed_export(model_name, model, provider_name, endpoint_value, api_key_value)
        if tool == "aider":
            return self._aider_export(model_name, model, provider_name, endpoint_value, api_key_value)
        if tool == "openai-compatible":
            return self._openai_compatible_export(model_name, model, provider_name, endpoint_value, api_key_value)
        raise ValueError(f"unknown integration: {tool}")

    def export_from_plan(self, plan: dict[str, Any]) -> IntegrationExport:
        tool = str(plan.get("tool") or "")
        if tool == "continue":
            return self._continue_export_from_plan(plan)
        if tool in MCP_EXPORT_TOOLS:
            return self._mcp_export(tool)
        if tool not in ONE_MODEL_TOOLS:
            raise ValueError(f"unknown integration in plan: {tool}")
        selection = plan.get("selection") if isinstance(plan.get("selection"), dict) else {}
        row = selection.get("primary") if isinstance(selection.get("primary"), dict) else None
        if not row:
            raise ValueError("saved plan does not contain a primary selection")
        model_name = str(row.get("name") or "selected-model")
        model = {"model": row.get("model")}
        provider_name = str(row.get("provider") or "")
        endpoint = str(row.get("endpoint") or "")
        api_key_env = str(row.get("api_key_env") or "")
        if tool == "cline":
            return self._cline_export(model_name, model, provider_name, endpoint, api_key_env)
        if tool == "zed":
            return self._zed_export(model_name, model, provider_name, endpoint, api_key_env)
        if tool == "aider":
            return self._aider_export(model_name, model, provider_name, endpoint, api_key_env)
        return self._openai_compatible_export(model_name, model, provider_name, endpoint, api_key_env)

    def plan(
        self,
        tool: str,
        model_name: str | None = None,
        provider: str | None = None,
        runtime: str | None = None,
        capabilities: list[str] | None = None,
        select_best: bool = False,
        chat: str | None = None,
        autocomplete: str | None = None,
        embedding: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
    ) -> dict[str, Any]:
        if tool in MCP_EXPORT_TOOLS:
            return {
                "name": "integration_plan",
                "tool": tool,
                "profile": self.profile.name,
                "required_roles": self._required_roles(tool),
                "selection": {},
                "notes": [
                    "MCP exports do not select an inference model; they configure a client to launch aiplane mcp serve.",
                    "Use integrations export for MCP config snippets.",
                ],
            }
        constraints = {
            "provider": provider,
            "runtime": runtime,
            "capabilities": expand_capability_filters(capabilities or []),
            "select_best": bool(select_best),
        }
        overrides = {"chat": chat, "autocomplete": autocomplete, "embedding": embedding}
        selection = {}
        if tool == "continue":
            roles = ["chat", "autocomplete", "embedding"]
            for role in roles:
                alias = overrides.get(role)
                if alias:
                    row = self._selection_row(
                        role,
                        alias,
                        "manual override",
                        endpoint=endpoint,
                        api_key_env=api_key_env,
                        runtime_constraint=runtime,
                    )
                elif select_best or provider or runtime or capabilities:
                    row = self._best_model_for_role(role, constraints, endpoint=endpoint, api_key_env=api_key_env)
                else:
                    default_role = f"{role}_model"
                    fallback = {
                        "chat": ("code_model", "self_managed_model"),
                        "autocomplete": ("completion_model", "code_model"),
                        "embedding": (),
                    }[role]
                    alias = self._default_model_name(default_role, *fallback)
                    row = self._selection_row(
                        role,
                        alias,
                        f"profile default {default_role}",
                        endpoint=endpoint,
                        api_key_env=api_key_env,
                        runtime_constraint=runtime,
                    )
                selection[role] = row
        else:
            if tool not in ONE_MODEL_TOOLS:
                raise ValueError(f"unknown integration: {tool}")
            if any(overrides.values()):
                raise ValueError("--chat, --autocomplete, and --embedding are only meaningful for Continue planning")
            if model_name:
                row = self._selection_row(
                    "chat",
                    model_name,
                    "manual model override",
                    endpoint=endpoint,
                    api_key_env=api_key_env,
                    runtime_constraint=runtime,
                )
            elif select_best or provider or runtime or capabilities:
                row = self._best_model_for_role("chat", constraints, endpoint=endpoint, api_key_env=api_key_env)
            else:
                alias = self._default_model_name("chat_model", "code_model", "self_managed_model")
                row = self._selection_row(
                    "chat",
                    alias,
                    "profile default chat_model",
                    endpoint=endpoint,
                    api_key_env=api_key_env,
                    runtime_constraint=runtime,
                )
            selection["primary"] = row
        return {
            "name": "integration_plan",
            "tool": tool,
            "profile": self.profile.name,
            "required_roles": self._required_roles(tool),
            "constraints": constraints,
            "overrides": {key: value for key, value in overrides.items() if value},
            "selection": selection,
            "notes": [
                "plan prints the model/runtime/endpoint decision; it does not write IDE config or start runtimes",
                "export uses the same selection logic to print target-tool configuration",
                "setup uses the same selection logic to prepare runtimes/models; use --dry-run to preview actions",
            ],
        }

    def setup(
        self,
        tool: str,
        model_name: str | None = None,
        provider: str | None = None,
        runtime: str | None = None,
        capabilities: list[str] | None = None,
        select_best: bool = False,
        chat: str | None = None,
        autocomplete: str | None = None,
        embedding: str | None = None,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        dry_run: bool = True,
        yes: bool = False,
    ) -> dict[str, Any]:
        if not dry_run and not yes:
            raise PermissionError(
                "integration setup changes runtimes/models; pass --dry-run to preview without executing"
            )
        plan = self.plan(
            tool,
            model_name=model_name,
            provider=provider,
            runtime=runtime,
            capabilities=capabilities or [],
            select_best=select_best,
            chat=chat,
            autocomplete=autocomplete,
            embedding=embedding,
            endpoint=endpoint,
            api_key_env=api_key_env,
        )
        actions = []
        seen_start: set[str] = set()
        seen_install: set[str] = set()
        seen_pull: set[str] = set()
        runtime_catalog = RuntimeCatalog(self.profile)
        for role, selected in plan["selection"].items():
            runtime_name = str(selected.get("runtime") or "")
            model_name = str(selected.get("name") or "")
            status = (
                runtime_catalog.runtime_available(runtime_name)
                if runtime_name
                else {"available": False, "reason": "no runtime selected"}
            )
            if runtime_name and runtime_name not in seen_start and not bool(status.get("available")):
                if runtime_name not in seen_install and self._runtime_install_needed(runtime_name):
                    actions.append(
                        self._setup_action(
                            runtime_name,
                            "install",
                            model_name,
                            dry_run=dry_run,
                            execute=not dry_run and yes,
                            reason="runtime helper install is supported and runtime is not installed",
                        )
                    )
                    seen_install.add(runtime_name)
                actions.append(
                    self._setup_action(
                        runtime_name,
                        "start",
                        model_name,
                        dry_run=dry_run,
                        execute=not dry_run and yes,
                        reason=status.get("reason"),
                    )
                )
                seen_start.add(runtime_name)
            model_status = self._model_presence(model_name)
            if not model_status["available"] and runtime_name:
                pull_key = f"{runtime_name}:{model_name}"
                if pull_key not in seen_pull:
                    pull_check = self._runtime_pull_support(runtime_name, selected)
                    if pull_check["supported"]:
                        actions.append(
                            self._setup_action(
                                runtime_name,
                                "pull",
                                model_name,
                                dry_run=dry_run,
                                execute=not dry_run and yes,
                                reason=model_status["reason"],
                            )
                        )
                    else:
                        actions.append(
                            {
                                "role": role,
                                "runtime": runtime_name,
                                "model": model_name,
                                "action": "pull",
                                "status": "skipped",
                                "reason": pull_check["reason"],
                                "model_status_reason": model_status["reason"],
                                "provider": selected.get("provider"),
                                "source": selected.get("source"),
                                "runtime_model": selected.get("model"),
                                "supported_pull_sources": pull_check["supported_sources"],
                            }
                        )
                    seen_pull.add(pull_key)
            else:
                actions.append(
                    {
                        "role": role,
                        "runtime": runtime_name,
                        "model": model_name,
                        "action": "check_model",
                        "status": "ok",
                        **model_status,
                    }
                )
        return {
            "name": "integration_setup",
            "tool": tool,
            "dry_run": dry_run,
            "executed": bool(not dry_run and yes),
            "plan": plan,
            "actions": actions,
            "notes": [
                "setup uses runtime helpers where available; dry-run previews delegated commands",
                "setup does not edit IDE config; run integrations export after setup succeeds",
            ],
        }

    def _required_roles(self, tool: str) -> list[dict[str, Any]]:
        return required_roles(tool)

    def _default_model_name(self, *roles: str) -> str:
        defaults = self.catalog.defaults()
        models = self.catalog.models()
        for role in roles:
            name = str(defaults.get(role) or "")
            if name and name in models:
                return name
        for name, model in models.items():
            if bool(model.get("enabled", True)):
                return name
        raise ValueError("no enabled model is configured in the selected profile")

    def _model_ref_for_role(
        self, role: str, fallback_roles: tuple[str, ...]
    ) -> tuple[str, dict[str, Any], str, str, str]:
        name = self._default_model_name(role, *fallback_roles)
        model = self.catalog.get(name)
        provider_name = str(model.get("provider"))
        endpoint = self._endpoint_for_provider(provider_name)
        api_key_env = self._api_key_env_for(model, provider_name)
        return name, model, provider_name, endpoint, api_key_env

    def _best_model_for_role(
        self,
        role: str,
        constraints: dict[str, Any],
        endpoint: str | None = None,
        api_key_env: str | None = None,
    ) -> dict[str, Any]:
        required_caps = dict(constraints.get("capabilities") or {})
        for capability in ROLE_CAPABILITY_MAP.get(role, []):
            required_caps.setdefault(capability, 1)
        filters = {
            "provider": constraints.get("provider"),
            "runtime": constraints.get("runtime"),
            "role": role,
            "enabled_only": True,
            "capabilities": required_caps,
        }
        rows = self.catalog.filter(filters)
        if not rows:
            filters["role"] = None
            rows = self.catalog.filter(filters)
        if not rows:
            raise ValueError(f"no enabled model matches role {role!r} and constraints")
        selected = max(rows, key=lambda row: (self._role_score(role, row), row.get("name", "")))
        return self._selection_row(
            role,
            str(selected["name"]),
            "best catalog match for role/capability constraints",
            endpoint=endpoint,
            api_key_env=api_key_env,
            runtime_constraint=constraints.get("runtime"),
        )

    def _selection_row(
        self,
        role: str,
        model_name: str,
        reason: str,
        endpoint: str | None = None,
        api_key_env: str | None = None,
        runtime_constraint: str | None = None,
    ) -> dict[str, Any]:
        model = self.catalog.get(model_name)
        runtime_catalog = RuntimeCatalog(self.profile)
        supported = runtime_catalog.supported_runtimes(model_name)
        if runtime_constraint:
            if runtime_constraint not in supported:
                raise ValueError(
                    f"runtime {runtime_constraint!r} is not supported by model {model_name!r}; supported: {', '.join(supported) or 'none'}"
                )
            runtime_name = runtime_constraint
        else:
            selected_runtime = runtime_catalog.select_runtime(model_name)
            runtime_name = str(
                selected_runtime.get("selected") or model.get("preferred_runtime") or model.get("provider") or ""
            )
        provider_name = str(model.get("provider") or "")
        endpoint_value = endpoint or self._endpoint_for_provider(
            runtime_name if runtime_name in self.catalog.providers() else provider_name
        )
        api_key_value = api_key_env or self._api_key_env_for(model, provider_name)
        capabilities = self.catalog.show(model_name)["capabilities"]
        return {
            "name": model_name,
            "role": role,
            "provider": provider_name,
            "runtime": runtime_name,
            "source": self.catalog.show(model_name).get("source"),
            "model": model.get("model"),
            "endpoint": endpoint_value,
            "api_key_env": api_key_value or None,
            "supported_runtimes": supported,
            "roles": model.get("roles", []),
            "capability_scores": capabilities.get("scores", {}),
            "role_capabilities": ROLE_CAPABILITY_MAP.get(role, []),
            "role_score": self._role_score(role, self.catalog.show(model_name)),
            "reason": reason,
        }

    def _role_score(self, role: str, row: dict[str, Any]) -> int:
        profile = row.get("capabilities", {}) if isinstance(row, dict) else {}
        scores = profile.get("scores", {}) if isinstance(profile, dict) else {}
        return sum(int(scores.get(capability, 0)) for capability in ROLE_CAPABILITY_MAP.get(role, []))

    def _model_presence(self, model_name: str) -> dict[str, Any]:
        statuses = {status.name: status for status in self.catalog.doctor()}
        status = statuses.get(model_name)
        if status is None:
            return {"available": False, "reason": "model is not configured"}
        return {
            "available": bool(status.usable),
            "reason": status.reason,
            "provider": status.provider,
        }

    def _runtime_install_needed(self, runtime: str) -> bool:
        if runtime == "ollama":
            return shutil.which("ollama") is None
        return False

    def _runtime_pull_support(self, runtime: str, selected: dict[str, Any]) -> dict[str, Any]:
        return runtime_pull_support(runtime, selected)

    def _setup_action(
        self,
        runtime: str,
        action: str,
        model_name: str,
        dry_run: bool,
        execute: bool,
        reason: object = None,
    ) -> dict[str, Any]:
        helper = Path(__file__).resolve().parents[2] / "scripts" / "provider_helper.sh"
        command = [
            "scripts/provider_helper.sh",
            "--provider",
            runtime,
            "--action",
            action,
            "--profile",
            self.profile.name,
            "--model",
            model_name,
        ]
        exec_command = [
            str(helper),
            "--provider",
            runtime,
            "--action",
            action,
            "--profile",
            self.profile.name,
            "--model",
            model_name,
        ]
        if dry_run:
            command.append("--dry-run")
            exec_command.append("--dry-run")
        row: dict[str, Any] = {
            "runtime": runtime,
            "model": model_name,
            "action": action,
            "reason": reason,
            "command": command,
            "status": "planned" if dry_run else "pending",
        }
        if execute:
            env = os.environ.copy()
            env["AIPLANE_PROFILES_DIR"] = str(self.profile.root.parent)
            completed = self._run_with_progress(
                exec_command,
                cwd=self.profile.workspace,
                label=f"setup: {action} {runtime} for {model_name}",
                env=env,
            )
            row.update(
                {
                    "status": "succeeded" if completed.returncode == 0 else "failed",
                    "returncode": completed.returncode,
                }
            )
            if completed.returncode != 0:
                row["stdout_tail"] = self._output_tail(completed.stdout)
                row["stderr_tail"] = self._output_tail(completed.stderr)
        return row

    @staticmethod
    def _run_with_progress(
        command: list[str], cwd: Path, label: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        sys.stderr.write(f"{label}\n")
        sys.stderr.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        streams = {
            process.stdout.fileno(): ("stdout", process.stdout),
            process.stderr.fileno(): ("stderr", process.stderr),
        }
        last_output = time.monotonic()
        wrote_progress = False
        while streams:
            readable, _, _ = select.select(list(streams), [], [], 2)
            if not readable:
                if process.poll() is None and time.monotonic() - last_output >= 2:
                    sys.stderr.write(".")
                    sys.stderr.flush()
                    wrote_progress = True
                continue
            for fd in readable:
                name, stream = streams[fd]
                chunk = os.read(fd, 4096)
                if not chunk:
                    stream.close()
                    streams.pop(fd, None)
                    continue
                buffers[name].extend(chunk)
                sys.stderr.write(chunk.decode(errors="replace"))
                sys.stderr.flush()
                last_output = time.monotonic()
                wrote_progress = True
        returncode = process.wait()
        if wrote_progress:
            sys.stderr.write("\n")
        sys.stderr.write(f"{label} {'done' if returncode == 0 else 'failed'}\n")
        sys.stderr.flush()
        stdout = buffers["stdout"].decode(errors="replace")
        stderr = buffers["stderr"].decode(errors="replace")
        return subprocess.CompletedProcess(command, int(returncode or 0), stdout, stderr)

    @staticmethod
    def _output_tail(value: str, limit: int = 12) -> list[str]:
        ansi_pattern = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        cleaned = ansi_pattern.sub("", value or "")
        cleaned = cleaned.replace("\r", "\n")
        lines = []
        for line in cleaned.splitlines():
            line = "".join(ch for ch in line if ch == "\t" or ord(ch) >= 32).strip()
            if line:
                lines.append(line)
        return lines[-limit:]

    def chat_command(self, model_name: str | None = None) -> list[str]:
        model_name = model_name or self._default_model_name("chat_model", "self_managed_model", "code_model")
        model = self.catalog.get(model_name)
        ollama_model_id = self._ollama_model_id(model)
        if not ollama_model_id:
            provider_name = str(model.get("provider") or "unknown")
            runtime = str(model.get("preferred_runtime") or provider_name or "unknown")
            supported = RuntimeCatalog(self.profile).supported_runtimes(model_name)
            raise ValueError(
                f"chat wrapper currently supports aliases that can run through local Ollama; "
                f"model {model_name!r} uses provider {provider_name!r}, preferred runtime {runtime!r}, "
                f"and supported runtimes {supported}. "
                "Select an alias with `aiplane models list --runtime ollama --role chat --name-only`."
            )
        return ["ollama", "run", ollama_model_id]

    def _ollama_model_id(self, model: dict[str, Any]) -> str:
        return ollama_model_id(self.profile, model)

    def run_chat(self, model_name: str | None = None, dry_run: bool = False) -> str:
        command = self.chat_command(model_name)
        if dry_run:
            return " ".join(command)
        subprocess.run(command, cwd=self.profile.workspace, check=True)
        return ""

    def _api_key_env_for(self, model: dict[str, Any], provider_name: str) -> str:
        provider = self.catalog.providers().get(provider_name, {})
        credential_ref = str(model.get("credential_ref") or provider.get("credential_ref") or "")
        if credential_ref:
            env_name = self.credentials.api_key_env(credential_ref)
            if env_name:
                return env_name
        return str(model.get("api_key_env") or provider.get("api_key_env") or "")

    def _endpoint_for_provider(self, provider_name: str) -> str:
        provider = self.catalog.providers().get(provider_name, {})
        credential_ref = str(provider.get("credential_ref") or "")
        credential_endpoint = self.credentials.endpoint(credential_ref) if credential_ref else None
        endpoint = str(provider.get("endpoint") or credential_endpoint or "")
        if provider_name in {"ollama", "ollama_cloud"}:
            if not endpoint:
                endpoint = "http://localhost:11434" if provider_name == "ollama" else "https://ollama.com"
            return endpoint.rstrip("/") + "/v1"
        if provider_name == "openai":
            return (endpoint or "https://api.openai.com/v1").rstrip("/")
        if provider_name == "anthropic":
            return (endpoint or "https://api.anthropic.com").rstrip("/")
        return endpoint.rstrip("/")

    def _continue_provider(self, provider_name: str) -> str:
        if provider_name == "anthropic":
            return "anthropic"
        return "openai"

    def _continue_export_from_plan(self, plan: dict[str, Any]) -> IntegrationExport:
        selection = plan["selection"]

        def api_key(row: dict[str, Any]) -> str:
            key_env = str(row.get("api_key_env") or "")
            return (
                "ollama" if row.get("provider") == "ollama" and not key_env else "${" + key_env + "}" if key_env else ""
            )

        chat = selection["chat"]
        completion = selection["autocomplete"]
        embedding = selection["embedding"]
        yaml = (
            "name: aiplane\n"
            "version: 0.1.0\n"
            "schema: v1\n"
            "models:\n"
            f"  - name: {chat['name']}\n"
            f"    provider: {self._continue_provider(str(chat.get('provider') or ''))}\n"
            f"    model: {chat['model']}\n"
            f"    apiBase: {chat['endpoint']}\n"
            f"    apiKey: {api_key(chat)}\n"
            "    roles: [chat, edit, apply]\n"
            f"  - name: {completion['name']}\n"
            f"    provider: {self._continue_provider(str(completion.get('provider') or ''))}\n"
            f"    model: {completion['model']}\n"
            f"    apiBase: {completion['endpoint']}\n"
            f"    apiKey: {api_key(completion)}\n"
            "    roles: [autocomplete]\n"
            "tabAutocompleteModel:\n"
            f"  title: {completion['name']}\n"
            f"  provider: {self._continue_provider(str(completion.get('provider') or ''))}\n"
            f"  model: {completion['model']}\n"
            f"  apiBase: {completion['endpoint']}\n"
            f"  apiKey: {api_key(completion)}\n"
            "embeddingsProvider:\n"
            f"  provider: {self._continue_provider(str(embedding.get('provider') or ''))}\n"
            f"  model: {embedding['model']}\n"
            f"  apiBase: {embedding['endpoint']}\n"
            f"  apiKey: {api_key(embedding)}\n"
        )
        notes = [
            "This exports a Continue starting point from the integration plan selection.",
            "Run integrations plan continue with the same constraints to inspect the decision.",
            "For Ollama, make sure the service is running and the selected models are pulled, or run integrations setup continue --dry-run.",
        ]
        return IntegrationExport("continue", "profile-defaults", "mixed", "planned endpoints", yaml, notes)

    def _continue_bundle_export(self, endpoint: str | None = None, api_key_env: str | None = None) -> IntegrationExport:
        chat_name, chat_model, chat_provider, chat_endpoint, chat_key_env = self._model_ref_for_role(
            "chat_model", ("code_model", "self_managed_model")
        )
        (
            completion_name,
            completion_model,
            completion_provider,
            completion_endpoint,
            completion_key_env,
        ) = self._model_ref_for_role("autocomplete_model", ("completion_model", "code_model"))
        (
            embedding_name,
            embedding_model,
            embedding_provider,
            embedding_endpoint,
            embedding_key_env,
        ) = self._model_ref_for_role("embedding_model", ())
        if endpoint:
            chat_endpoint = completion_endpoint = embedding_endpoint = endpoint
        if api_key_env is not None:
            chat_key_env = completion_key_env = embedding_key_env = api_key_env

        def api_key(provider_name: str, key_env: str) -> str:
            return "ollama" if provider_name == "ollama" and not key_env else "${" + key_env + "}" if key_env else ""

        yaml = (
            "name: aiplane\n"
            "version: 0.1.0\n"
            "schema: v1\n"
            "models:\n"
            f"  - name: {chat_name}\n"
            f"    provider: {self._continue_provider(chat_provider)}\n"
            f"    model: {chat_model.get('model')}\n"
            f"    apiBase: {chat_endpoint}\n"
            f"    apiKey: {api_key(chat_provider, chat_key_env)}\n"
            "    roles: [chat, edit, apply]\n"
            f"  - name: {completion_name}\n"
            f"    provider: {self._continue_provider(completion_provider)}\n"
            f"    model: {completion_model.get('model')}\n"
            f"    apiBase: {completion_endpoint}\n"
            f"    apiKey: {api_key(completion_provider, completion_key_env)}\n"
            "    roles: [autocomplete]\n"
            "tabAutocompleteModel:\n"
            f"  title: {completion_name}\n"
            f"  provider: {self._continue_provider(completion_provider)}\n"
            f"  model: {completion_model.get('model')}\n"
            f"  apiBase: {completion_endpoint}\n"
            f"  apiKey: {api_key(completion_provider, completion_key_env)}\n"
            "embeddingsProvider:\n"
            f"  provider: {self._continue_provider(embedding_provider)}\n"
            f"  model: {embedding_model.get('model')}\n"
            f"  apiBase: {embedding_endpoint}\n"
            f"  apiKey: {api_key(embedding_provider, embedding_key_env)}\n"
        )
        notes = [
            "This exports a Continue starting point using profile defaults: chat_model, autocomplete_model, and embedding_model.",
            "Paste/merge the YAML into your Continue config. It does not install Continue or edit files.",
            "For Ollama, make sure the service is running and the selected models are pulled.",
        ]
        return IntegrationExport(
            "continue",
            "profile-defaults",
            "mixed",
            endpoint or "profile endpoints",
            yaml,
            notes,
        )

    def _continue_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
    ) -> IntegrationExport:
        api_key = (
            "ollama"
            if provider_name == "ollama" and not api_key_env
            else "${" + api_key_env + "}"
            if api_key_env
            else ""
        )
        yaml = (
            "models:\n"
            f"  - name: {model_name}\n"
            f"    provider: {self._continue_provider(provider_name)}\n"
            f"    model: {model.get('model')}\n"
            f"    apiBase: {endpoint}\n"
            f"    apiKey: {api_key}\n"
            "    roles: [chat, edit, apply]\n"
        )
        notes = [
            "This command prints configuration only; it does not install or modify Continue.",
            "Paste this into the relevant Continue config file for your installation.",
            "The provider is set to openai because Ollama and many gateways expose OpenAI-compatible endpoints.",
        ]
        if endpoint.startswith("http://") and "localhost" not in endpoint and "127.0.0.1" not in endpoint:
            notes.append("Remote HTTP endpoints should normally be protected with TLS/auth before team use.")
        return IntegrationExport("continue", model_name, provider_name, endpoint, yaml, notes)

    def _mcp_export(self, tool: str) -> IntegrationExport:
        args = ["mcp", "serve"]
        if tool == "vscode-mcp":
            payload = {
                "servers": {
                    "aiplane": {
                        "type": "stdio",
                        "command": "aiplane",
                        "args": args,
                    }
                }
            }
            content = json_dumps(payload, indent=2)
            notes = [
                "Use this in .vscode/mcp.json or another VS Code MCP client config that accepts the servers shape."
            ]
        elif tool == "continue-mcp":
            content = (
                "name: aiplane\n"
                "version: 0.1.0\n"
                "schema: v1\n"
                "mcpServers:\n"
                "  - name: aiplane\n"
                "    type: stdio\n"
                "    command: aiplane\n"
                "    args:\n"
                "      - mcp\n"
                "      - serve\n"
            )
            notes = [
                "Use this in Continue's MCP/server config area. This is separate from Continue model endpoint config."
            ]
        else:
            payload = {
                "mcpServers": {
                    "aiplane": {
                        "command": "aiplane",
                        "args": args,
                    }
                }
            }
            content = json_dumps(payload, indent=2)
            notes = ["Use this with MCP clients that accept the common mcpServers JSON shape."]
            if tool == "cline-mcp":
                notes.append("Cline versions differ; map this into the MCP server settings for your installed version.")
        notes.append(
            "The MCP server lets clients query aiplane configuration and guarded tools; it is not the model inference endpoint."
        )
        notes.append("Profile selection uses the normal aiplane default rules unless you add --profile to the args.")
        return IntegrationExport(tool, "mcp", "aiplane", "stdio", content, notes)

    def _cline_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
    ) -> IntegrationExport:
        payload = {
            "name": model_name,
            "provider": "openai-compatible",
            "model": model.get("model"),
            "baseUrl": endpoint,
            "apiKeyEnv": api_key_env or None,
        }
        notes = [
            "Use this as the provider/model values in Cline where OpenAI-compatible providers are supported.",
            "The exact settings location can vary by Cline version and client surface.",
        ]
        return IntegrationExport(
            "cline",
            model_name,
            provider_name,
            endpoint,
            json_dumps(payload, indent=2),
            notes,
        )

    def _zed_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
    ) -> IntegrationExport:
        payload = {
            "assistant": {
                "provider": "openai-compatible",
                "model": {
                    "name": model_name,
                    "model": model.get("model"),
                    "base_url": endpoint,
                    "api_key_env": api_key_env or None,
                },
            }
        }
        notes = [
            "Use this as a starting point for Zed assistant/provider settings.",
            "Prefer the generic OpenAI-compatible endpoint when the runtime is Ollama, vLLM, llama.cpp, LM Studio, TGI, or LocalAI.",
        ]
        return IntegrationExport(
            "zed",
            model_name,
            provider_name,
            endpoint,
            json_dumps(payload, indent=2),
            notes,
        )

    def _aider_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
    ) -> IntegrationExport:
        key_value = f"${api_key_env}" if api_key_env else "dummy-local-key"
        content = (
            f"export OPENAI_API_BASE={endpoint}\n"
            f"export OPENAI_API_KEY={key_value}\n"
            f"aider --model openai/{model.get('model')}\n"
        )
        notes = [
            "Aider is CLI-first; this export prints environment variables and a launch command.",
            "For local Ollama/OpenAI-compatible endpoints, a dummy API key is often accepted by the local server.",
        ]
        return IntegrationExport("aider", model_name, provider_name, endpoint, content, notes)

    def _openai_compatible_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
    ) -> IntegrationExport:
        payload = {
            "name": model_name,
            "provider": provider_name,
            "model": model.get("model"),
            "base_url": endpoint,
            "api_key_env": api_key_env or None,
        }
        return IntegrationExport(
            "openai-compatible",
            model_name,
            provider_name,
            endpoint,
            json_dumps(payload, indent=2),
            ["Generic OpenAI-compatible config payload."],
        )
