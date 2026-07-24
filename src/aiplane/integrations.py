from __future__ import annotations

import json
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
from urllib.parse import urlsplit, urlunsplit

from .boundaries import CommandRunner, SubprocessCommandRunner
from .config import provider_helper_path
from .evidence import evidence_provenance, evidence_source
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
    content_format: str = "text"


class IntegrationManager:
    def __init__(self, profile: Profile, command_runner: CommandRunner | None = None):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
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
        output_format: str | None = None,
        api_type: str | None = None,
        offline: bool = False,
    ) -> IntegrationExport:
        self._validate_target_options(tool, output_format, api_type, offline)
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
                output_format=output_format,
                api_type=api_type,
                offline=offline,
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
        if tool in {"codex", "copilot-cli", "copilot-vscode"}:
            return self._host_client_export(
                tool,
                model_name,
                model,
                provider_name,
                endpoint_value,
                api_key_value,
                output_format,
                api_type,
                offline,
            )
        raise ValueError(f"unknown integration: {tool}")

    def export_from_plan(self, plan: Any) -> IntegrationExport:
        if not isinstance(plan, dict):
            raise ValueError("saved plan must be a JSON object produced by integrations plan")
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
        options = plan.get("target_options") if isinstance(plan.get("target_options"), dict) else {}
        if tool in {"codex", "copilot-cli", "copilot-vscode"}:
            model.update(
                {
                    key: row.get(key)
                    for key in (
                        "context_window_tokens",
                        "max_output_tokens",
                        "supports_tool_calling",
                        "supports_streaming",
                        "capability_scores",
                        "supported_apis",
                    )
                }
            )
            return self._host_client_export(
                tool,
                model_name,
                model,
                provider_name,
                endpoint,
                api_key_env,
                options.get("format"),
                options.get("api_type"),
                bool(options.get("offline")),
            )
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
        output_format: str | None = None,
        api_type: str | None = None,
        offline: bool = False,
    ) -> dict[str, Any]:
        self._validate_target_options(tool, output_format, api_type, offline)
        if tool in MCP_EXPORT_TOOLS:
            return {
                "name": "integration_plan",
                "tool": tool,
                "profile": self.profile.name,
                "required_roles": self._required_roles(tool),
                "selection": {},
                "compatibility": {
                    "status": "compatible",
                    "warnings": [],
                    "renderable": True,
                    "next_command": "aiplane integrations export " + tool,
                },
                "provenance": evidence_provenance(
                    [evidence_source("integration_contract", "generated", "integration_contracts", value=tool)],
                    method="mcp_contract_export",
                ),
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
        if tool in {"codex", "copilot-cli", "copilot-vscode"}:
            selected = selection["primary"]
            selected_model = dict(self.catalog.get(str(selected["name"])))
            selected_model["capability_scores"] = selected.get("capability_scores", {})
            selected_model["supported_apis"] = selected.get("supported_apis", [])
            selected["compatibility_warnings"] = self._agent_warnings(
                tool,
                str(selected["name"]),
                selected_model,
            )
            selected["selected_api_type"] = self._select_api_type(
                tool,
                str(selected["provider"]),
                selected_model,
                api_type,
            )
        return {
            "name": "integration_plan",
            "tool": tool,
            "profile": self.profile.name,
            "required_roles": self._required_roles(tool),
            "constraints": constraints,
            "overrides": {key: value for key, value in overrides.items() if value},
            "target_options": {
                "format": output_format,
                "api_type": api_type,
                "offline": bool(offline),
            },
            "selection": selection,
            "compatibility": self._plan_compatibility(tool, selection),
            "provenance": self._plan_provenance(selection, constraints, overrides, endpoint),
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
        output_format: str | None = None,
        api_type: str | None = None,
        offline: bool = False,
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
            output_format=output_format,
            api_type=api_type,
            offline=offline,
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

    def _plan_compatibility(self, tool: str, selection: dict[str, dict[str, Any]]) -> dict[str, Any]:
        warnings: list[dict[str, str]] = []
        for role, row in selection.items():
            for warning in (
                row.get("compatibility_warnings", []) if isinstance(row.get("compatibility_warnings"), list) else []
            ):
                warnings.append({"role": role, "model": str(row.get("name") or ""), "message": str(warning)})
            if not row.get("runtime") and tool not in MCP_EXPORT_TOOLS:
                warnings.append(
                    {
                        "role": role,
                        "model": str(row.get("name") or ""),
                        "message": "No local runtime was selected; verify the managed endpoint or provider configuration.",
                    }
                )
        return {
            "status": "warnings" if warnings else "compatible",
            "warnings": warnings,
            "renderable": True,
            "next_command": "aiplane integrations export " + tool,
        }

    def _plan_provenance(
        self,
        selection: dict[str, dict[str, Any]],
        constraints: dict[str, Any],
        overrides: dict[str, str | None],
        endpoint: str | None,
    ) -> dict[str, Any]:
        sources = [evidence_source("selection_rules", "generated", "model_catalog")]
        uncertainty: list[str] = []
        if any(value for value in constraints.values()) or any(overrides.values()):
            sources.append(evidence_source("selection_constraints", "configured", "command_line"))
        if endpoint:
            sources.append(evidence_source("endpoint", "configured", "command_line", value=endpoint))
        for role, row in selection.items():
            origin = str(row.get("source") or "")
            state = (
                "discovered"
                if origin == "discovered_cache"
                else "configured"
                if origin == "profile_configured"
                else "generated"
            )
            sources.append(evidence_source(f"model.{role}", state, origin or "model_catalog", value=row.get("name")))
            sources.append(evidence_source(f"runtime.{role}", "generated", "runtime_catalog", value=row.get("runtime")))
            if not row.get("runtime"):
                uncertainty.append(f"no runtime could be selected for {role}")
        uncertainty.append("catalog capability scores are configured metadata, not measured task-quality evidence")
        return evidence_provenance(
            sources,
            uncertainty=uncertainty,
            method="deterministic_role_and_capability_selection",
        )

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
        capability_scores = capabilities.get("scores", {})
        context_window = model.get("context_window_tokens") or self._token_count(model.get("context"))
        tool_calling = model.get("supports_tool_calling")
        if tool_calling is None and int(capability_scores.get("tool_use", 0) or 0) > 0:
            tool_calling = True
        provider = self.catalog.providers().get(provider_name, {})
        supported_apis = provider.get("supported_apis")
        if not isinstance(supported_apis, list):
            supported_apis = self._default_supported_apis(provider_name, str(provider.get("protocol") or ""))
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
            "capability_scores": capability_scores,
            "context_window_tokens": context_window,
            "max_output_tokens": model.get("max_output_tokens"),
            "supports_tool_calling": tool_calling,
            "supports_streaming": model.get("supports_streaming"),
            "supported_apis": supported_apis,
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
        helper = provider_helper_path()
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

    def _run_with_progress(
        self, command: list[str], cwd: Path, label: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if os.name == "nt":
            raise RuntimeError(
                "integration setup execution is unsupported on Windows; run in Linux/macOS or use --dry-run"
            )
        sys.stderr.write(f"{label}\n")
        sys.stderr.flush()
        process = self.command_runner.popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("integration setup helper must expose both stdout and stderr pipes")
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
        model_name = self._chat_model_name(model_name)
        model = self.catalog.get(model_name)
        self.catalog.require_execution_capability(model_name, model, "chat")
        ollama_model_id = self._ollama_model_id(model)
        if not ollama_model_id:
            provider_name = str(model.get("provider") or "unknown")
            runtime = str(model.get("preferred_runtime") or provider_name or "unknown")
            supported = RuntimeCatalog(self.profile).supported_runtimes(model_name)
            raise ValueError(
                f"native Ollama chat requires an alias that can run through local Ollama; "
                f"model {model_name!r} uses provider {provider_name!r}, preferred runtime {runtime!r}, "
                f"and supported runtimes {supported}. "
                "Use endpoint chat without --native-ollama, or select an alias with "
                "`aiplane models list --runtime ollama --role chat --identity alias`."
            )
        return ["ollama", "run", ollama_model_id]

    def chat_plan(self, model_name: str | None = None, prompt: str | None = None) -> dict[str, Any]:
        model_name = self._chat_model_name(model_name)
        model = self.catalog.get(model_name)
        self.catalog.require_execution_capability(model_name, model, "chat")
        provider_name = str(model.get("provider") or "")
        provider = self.catalog.providers().get(provider_name, {})
        supported = RuntimeCatalog(self.profile).supported_runtimes(model_name)
        runtime = (
            provider_name
            if provider.get("ownership") == "managed_service"
            else str(model.get("preferred_runtime") or (supported[0] if supported else provider_name))
        )
        protocol = str(provider.get("protocol") or ("ollama_api" if runtime == "ollama" else "openai_compatible"))
        return {
            "name": "chat_plan",
            "profile": self.profile.name,
            "model": model_name,
            "provider": provider_name,
            "runtime": runtime,
            "protocol": protocol,
            "endpoint": str(provider.get("endpoint") or ""),
            "prompt": prompt or "",
            "notes": [
                "Endpoint chat uses the same protocol backend as `aiplane run` and `aiplane models test`.",
                "It does not install runtimes or pull model weights; run runtime/setup commands first when needed.",
            ],
        }

    def _chat_model_name(self, model_name: str | None = None) -> str:
        return model_name or self._default_model_name("chat_model", "self_managed_model", "code_model")

    def _ollama_model_id(self, model: dict[str, Any]) -> str:
        return ollama_model_id(self.profile, model)

    def run_chat(
        self,
        model_name: str | None = None,
        prompt: str | None = None,
        dry_run: bool = False,
        timeout_seconds: int | None = None,
        native_ollama: bool = False,
    ) -> str:
        if native_ollama:
            command = self.chat_command(model_name)
            if dry_run:
                return " ".join(command)
            self.command_runner.run(command, cwd=self.profile.workspace, check=True)
            return ""

        model_name = self._chat_model_name(model_name)
        if dry_run:
            return json_dumps(self.chat_plan(model_name, prompt), indent=2, sort_keys=True)
        if prompt is None or not prompt.strip():
            raise ValueError("endpoint chat requires a prompt; pass --prompt, --stdin, or run from an interactive TTY")
        result = self.catalog.complete(model_name, prompt, timeout_seconds=timeout_seconds, purpose="chat")
        return result.text

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
        return IntegrationExport(
            tool,
            "mcp",
            "aiplane",
            "stdio",
            content,
            notes,
            "text" if tool == "continue-mcp" else "json",
        )

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
            "json",
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
            "json",
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

    @staticmethod
    def _validate_target_options(
        tool: str,
        output_format: str | None,
        api_type: str | None,
        offline: bool,
    ) -> None:
        host_tools = {"codex", "copilot-cli", "copilot-vscode"}
        if tool not in host_tools and (output_format or api_type or offline):
            raise ValueError("--format, --api-type, and --offline are only supported by host-client exports")
        if offline and tool != "copilot-cli":
            raise ValueError("--offline is only supported for copilot-cli")
        supported_formats = {
            "codex": {None, "native", "toml"},
            "copilot-cli": {None, "native", "json", "posix", "powershell"},
            "copilot-vscode": {None, "native", "json"},
        }
        if tool in host_tools and output_format not in supported_formats[tool]:
            rendered = ", ".join(sorted(value for value in supported_formats[tool] if value))
            raise ValueError(f"{tool} --format must be one of: {rendered}")

    def _host_client_export(
        self,
        tool: str,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        output_format: str | None,
        api_type: str | None,
        offline: bool,
    ) -> IntegrationExport:
        model = dict(model)
        if not isinstance(model.get("capability_scores"), dict):
            model["capability_scores"] = self.catalog.show(model_name)["capabilities"].get("scores", {})
        warnings = self._agent_warnings(tool, model_name, model)
        selected_api = self._select_api_type(tool, provider_name, model, api_type)
        if tool == "codex":
            if output_format not in {None, "native", "toml"}:
                raise ValueError("codex export supports only the native TOML format")
            if offline:
                raise ValueError("--offline is only supported for copilot-cli")
            return self._codex_export(model_name, model, provider_name, endpoint, api_key_env, selected_api, warnings)
        if tool == "copilot-cli":
            return self._copilot_cli_export(
                model_name,
                model,
                provider_name,
                endpoint,
                api_key_env,
                output_format or "json",
                offline,
                warnings,
            )
        if output_format not in {None, "native", "json"}:
            raise ValueError("copilot-vscode export supports only JSON")
        if offline:
            raise ValueError("--offline is only supported for copilot-cli")
        return self._copilot_vscode_export(
            model_name,
            model,
            provider_name,
            endpoint,
            api_key_env,
            selected_api,
            warnings,
        )

    def _agent_warnings(self, tool: str, model_name: str, model: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        tool_calling = model.get("supports_tool_calling")
        scores = model.get("capability_scores") if isinstance(model.get("capability_scores"), dict) else {}
        if tool_calling is None and int(scores.get("tool_use", 0) or 0) > 0:
            tool_calling = True
            warnings.append(
                "Tool-calling support is inferred from the catalog tool_use score; verify it with the client."
            )
        if tool_calling is False:
            raise ValueError(f"{tool} requires tool calling, but model {model_name!r} is marked incompatible")
        if tool_calling is None:
            warnings.append("Tool-calling support is unknown; agent mode may reject this model.")
        streaming = model.get("supports_streaming")
        if tool == "copilot-cli" and streaming is False:
            raise ValueError(f"copilot-cli requires streaming, but model {model_name!r} is marked incompatible")
        if streaming is None:
            warnings.append("Streaming support is unknown; verify the selected endpoint before agent use.")
        context = self._token_count(model.get("context_window_tokens") or model.get("context"))
        if context is None:
            warnings.append("Context-window size is unknown.")
        elif tool == "copilot-cli" and context < 128000:
            warnings.append(f"Context window is {context} tokens; GitHub recommends at least 128000 for Copilot CLI.")
        return warnings

    def _select_api_type(
        self,
        tool: str,
        provider_name: str,
        model: dict[str, Any],
        override: str | None,
    ) -> str:
        normalized_override = str(override or "").replace("-", "_")
        allowed = {"responses", "chat_completions", "messages"}
        if normalized_override and normalized_override not in allowed:
            raise ValueError("--api-type must be responses, chat-completions, or messages")
        configured = model.get("supported_apis")
        if not isinstance(configured, list):
            provider = self.catalog.providers().get(provider_name, {})
            configured = provider.get("supported_apis")
            if not isinstance(configured, list):
                configured = self._default_supported_apis(provider_name, str(provider.get("protocol") or ""))
        supported = {str(value).replace("-", "_") for value in configured}
        if normalized_override:
            selected = normalized_override
        elif provider_name == "anthropic":
            selected = "messages"
        elif tool == "codex":
            selected = "responses"
        elif tool == "copilot-cli":
            selected = "chat_completions"
        elif "responses" in supported:
            selected = "responses"
        elif "chat_completions" in supported:
            selected = "chat_completions"
        elif "messages" in supported:
            selected = "messages"
        else:
            raise ValueError(f"provider {provider_name!r} has no supported host-client API metadata; pass --api-type")
        if provider_name != "ollama" and supported and selected not in supported:
            raise ValueError(
                f"provider {provider_name!r} does not declare {selected.replace('_', '-')} support; "
                f"supported: {', '.join(sorted(value.replace('_', '-') for value in supported))}"
            )
        if tool == "codex" and provider_name != "ollama" and selected != "responses":
            raise ValueError(
                "Codex custom providers require the Responses API; use a Responses-compatible gateway such as LiteLLM"
            )
        if (
            tool == "copilot-cli"
            and provider_name not in {"anthropic", "azure_openai"}
            and selected != "chat_completions"
        ):
            raise ValueError("Copilot CLI OpenAI-compatible BYOK endpoints require Chat Completions")
        return selected

    @staticmethod
    def _default_supported_apis(provider_name: str, protocol: str) -> list[str]:
        if provider_name == "openai":
            return ["responses", "chat_completions"]
        if provider_name == "anthropic" or protocol in {"anthropic_api", "anthropic_messages"}:
            return ["messages"]
        if provider_name == "azure_openai" or protocol == "azure_openai":
            return ["responses", "chat_completions"]
        if provider_name == "ollama" or protocol in {"ollama_api", "openai_compatible"}:
            return ["chat_completions"]
        return []

    @staticmethod
    def _token_count(value: object) -> int | None:
        if value in {None, ""}:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip().lower().replace(",", "")
        multiplier = 1
        if text.endswith("k"):
            multiplier, text = 1000, text[:-1]
        elif text.endswith("m"):
            multiplier, text = 1000000, text[:-1]
        try:
            return int(float(text) * multiplier)
        except ValueError:
            return None

    @staticmethod
    def _client_slug(model_name: str) -> str:
        slug = re.sub(r"[^a-z0-9_-]+", "-", model_name.lower()).strip("-_")
        return f"aiplane-{slug or 'model'}"

    def _codex_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        api_type: str,
        warnings: list[str],
    ) -> IntegrationExport:
        profile_id = self._client_slug(model_name)
        model_id = str(model.get("model") or "")
        if provider_name == "ollama":
            hostname = (urlsplit(endpoint).hostname or "").lower()
            if hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError(
                    "Codex built-in Ollama configuration is local-only; use a Responses-compatible gateway for remote Ollama"
                )
            content = (
                f'[profiles.{json.dumps(profile_id)}]\nmodel = {json.dumps(model_id)}\nmodel_provider = "ollama"\n'
            )
        else:
            provider_id = profile_id
            content = (
                f"[model_providers.{json.dumps(provider_id)}]\n"
                f"name = {json.dumps('Aiplane: ' + model_name)}\n"
                f"base_url = {json.dumps(endpoint.rstrip('/'))}\n"
                + (f"env_key = {json.dumps(api_key_env)}\n" if api_key_env else "")
                + f"wire_api = {json.dumps(api_type)}\n\n"
                + f"[profiles.{json.dumps(profile_id)}]\n"
                + f"model = {json.dumps(model_id)}\n"
                + f"model_provider = {json.dumps(provider_id)}\n"
            )
        notes = [
            "Merge this into the user-level ~/.codex/config.toml; repository provider overrides are not supported.",
            f"Start the CLI with: codex --profile {profile_id}",
            "The named profile preserves the current Codex default; IDE profile activation depends on the installed Codex version.",
            *warnings,
        ]
        return IntegrationExport("codex", model_name, provider_name, endpoint, content, notes, "toml")

    def _copilot_cli_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        output_format: str,
        offline: bool,
        warnings: list[str],
    ) -> IntegrationExport:
        output_format = "json" if output_format == "native" else output_format
        if output_format not in {"json", "posix", "powershell"}:
            raise ValueError("copilot-cli --format must be json, posix, or powershell")
        provider_type = (
            "anthropic" if provider_name == "anthropic" else "azure" if provider_name == "azure_openai" else "openai"
        )
        base_url = endpoint.rstrip("/")
        if provider_name == "ollama" and base_url.endswith("/v1"):
            base_url = base_url[:-3]
        environment = {
            "COPILOT_PROVIDER_BASE_URL": base_url,
            "COPILOT_PROVIDER_TYPE": provider_type,
            "COPILOT_MODEL": str(model.get("model") or ""),
        }
        if offline:
            environment["COPILOT_OFFLINE"] = "true"
        environment_refs = {"COPILOT_PROVIDER_API_KEY": api_key_env} if api_key_env else {}
        notes = [
            "Plugins, built-in sub-agents, skills, and MCP tools inherit this host-session provider and model.",
            "GitHub authentication is still required for GitHub-backed delegation, code search, and the GitHub MCP server.",
            *warnings,
        ]
        payload = {
            "alias": model_name,
            "model": str(model.get("model") or ""),
            "provider": provider_name,
            "environment": environment,
            "environment_refs": environment_refs,
            "command": ["copilot"],
            "warnings": warnings,
            "notes": notes[:2],
        }
        if output_format == "json":
            return IntegrationExport(
                "copilot-cli",
                model_name,
                provider_name,
                base_url,
                json_dumps(payload, indent=2),
                [],
                "json",
            )
        if output_format == "posix":
            lines = [f"export {key}={json.dumps(value)}" for key, value in environment.items()]
            lines.extend(f'export {target}="${{{source}}}"' for target, source in environment_refs.items())
            lines.append("copilot")
        else:

            def ps(value: str) -> str:
                return "'" + value.replace("'", "''") + "'"

            lines = [f"$env:{key} = {ps(value)}" for key, value in environment.items()]
            lines.extend(f"$env:{target} = $env:{source}" for target, source in environment_refs.items())
            lines.append("copilot")
        return IntegrationExport(
            "copilot-cli",
            model_name,
            provider_name,
            base_url,
            "\n".join(lines) + "\n",
            notes,
            output_format,
        )

    @staticmethod
    def _endpoint_with_suffix(endpoint: str, suffix: str, *, trim_v1: bool = False) -> str:
        parsed = urlsplit(endpoint)
        path = parsed.path.rstrip("/")
        if trim_v1 and path.endswith("/v1"):
            path = path[:-3]
        if not path.endswith(suffix):
            path += suffix
        return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))

    def _copilot_vscode_export(
        self,
        model_name: str,
        model: dict[str, Any],
        provider_name: str,
        endpoint: str,
        api_key_env: str,
        api_type: str,
        warnings: list[str],
    ) -> IntegrationExport:
        api_name = api_type.replace("_", "-")
        suffix = {"responses": "/responses", "chat-completions": "/chat/completions", "messages": "/v1/messages"}[
            api_name
        ]
        base = self._endpoint_with_suffix(endpoint, suffix, trim_v1=api_name == "messages")
        context = self._token_count(model.get("context_window_tokens") or model.get("context"))
        max_output = self._token_count(model.get("max_output_tokens"))
        model_row: dict[str, Any] = {
            "id": str(model.get("model") or ""),
            "name": model_name,
            "url": base,
            "apiType": api_name,
        }
        tool_calling = model.get("supports_tool_calling")
        scores = model.get("capability_scores") if isinstance(model.get("capability_scores"), dict) else {}
        if tool_calling is None and int(scores.get("tool_use", 0) or 0) > 0:
            tool_calling = True
        if tool_calling is not None:
            model_row["toolCalling"] = bool(tool_calling)
        if model.get("supports_streaming") is not None:
            model_row["streaming"] = bool(model.get("supports_streaming"))
        if context and max_output and context > max_output:
            model_row["maxInputTokens"] = context - max_output
            model_row["maxOutputTokens"] = max_output
        payload: dict[str, Any] = {
            "name": f"Aiplane: {model_name}",
            "vendor": "customendpoint",
            "apiType": api_name,
            "models": [model_row],
        }
        notes = [
            "Merge this provider object into VS Code chatLanguageModels.json through Manage Language Models.",
            "BYOK applies to chat, agents, and utility models, not inline completions, semantic search, or embeddings.",
            *warnings,
        ]
        if api_key_env:
            notes.insert(
                1,
                f"Enter the key referenced by {api_key_env} in VS Code Manage Language Models; it is not printed here.",
            )
        if provider_name == "ollama":
            notes.append(
                "VS Code recommends the official Ollama extension for the maintained local Ollama provider path."
            )
        return IntegrationExport(
            "copilot-vscode",
            model_name,
            provider_name,
            base,
            json_dumps([payload], indent=2),
            notes,
            "json",
        )

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
            "json",
        )
