from __future__ import annotations

import json
import sys
from pathlib import Path as FsPath
from typing import Any

from .audit import AuditLogger
from .config import list_profiles, load_profile, resolve_profile_name
from .hardware import HardwareManager
from .integration_contracts import ALL_INTEGRATION_TOOLS
from .integrations import IntegrationManager
from .machines import MachineManager
from .machine_model_filters import merge_machine_model_filters
from .model_catalog import ModelCatalog
from .runtime_catalog import RuntimeCatalog
from .stacks import StackManager
from .model_filters import (
    MODEL_FILTER_SCHEMA_PROPERTIES,
    MODEL_SORT_CHOICES,
    model_filter_args,
)
from .output import json_dumps
from .orchestrators import OrchestratorCatalog
from .providers import ProviderRegistry
from .remote import RemoteManager
from .models import AuditEvent, Profile


READ_ONLY_TOOLS: list[dict[str, Any]] = [
    {
        "name": "aiplane.docs.list",
        "description": "List project documentation and guidance files available to MCP clients.",
        "mutates": False,
    },
    {
        "name": "aiplane.docs.read",
        "description": "Read one documentation/help file by relative path.",
        "mutates": False,
    },
    {
        "name": "aiplane.profiles.list",
        "description": "List configured aiplane profiles.",
        "mutates": False,
    },
    {
        "name": "aiplane.providers.list",
        "description": "List configured providers and endpoints without secrets.",
        "mutates": False,
    },
    {
        "name": "aiplane.providers.models",
        "description": "Discover or list models available from a configured provider.",
        "mutates": False,
    },
    {
        "name": "aiplane.models.defaults",
        "description": "Show configured default model aliases by role.",
        "mutates": False,
    },
    {
        "name": "aiplane.models.list",
        "description": "List approved model catalog entries with capability scores.",
        "mutates": False,
    },
    {
        "name": "aiplane.models.show",
        "description": "Show one approved model entry with provider config and capability scores.",
        "mutates": False,
    },
    {
        "name": "aiplane.hardware.discover",
        "description": "Discover local CPU/RAM/GPU resources and matching hardware templates.",
        "mutates": False,
    },
    {
        "name": "aiplane.hardware.recommend",
        "description": "Return hardware-aware model recommendations.",
        "mutates": False,
    },
    {
        "name": "aiplane.machines.list",
        "description": "List configured machine profiles without contacting cloud APIs.",
        "mutates": False,
    },
    {
        "name": "aiplane.machines.show",
        "description": "Show one configured machine profile.",
        "mutates": False,
    },
    {
        "name": "aiplane.machines.recommend",
        "description": "Recommend configured machines for a model, runtime, or workload.",
        "mutates": False,
    },
    {
        "name": "aiplane.stacks.list",
        "description": "List configured stacks and their model/runtime/machine bindings.",
        "mutates": False,
    },
    {
        "name": "aiplane.stacks.show",
        "description": "Show one configured stack definition.",
        "mutates": False,
    },
    {
        "name": "aiplane.stacks.plan",
        "description": "Plan stack preparation steps and preflight checks without executing them.",
        "mutates": False,
    },
    {
        "name": "aiplane.stacks.doctor",
        "description": "Run stack readiness checks without executing lifecycle actions.",
        "mutates": False,
    },
    {
        "name": "aiplane.stacks.export",
        "description": "Export stack IDE, packaging, or orchestrator framework starter artifacts without writing files.",
        "mutates": False,
    },
    {
        "name": "aiplane.integrations.export",
        "description": "Generate IDE/CLI config snippets for a selected model endpoint.",
        "mutates": False,
    },
    {
        "name": "aiplane.integrations.roles",
        "description": "Show required and optional model roles for an integration target.",
        "mutates": False,
    },
    {
        "name": "aiplane.integrations.plan",
        "description": "Plan model/runtime/endpoint selection for an integration target without writing config or starting runtimes.",
        "mutates": False,
    },
    {
        "name": "aiplane.orchestrators.list",
        "description": "List supported orchestrator frameworks and their provider/runtime compatibility.",
        "mutates": False,
    },
    {
        "name": "aiplane.orchestrators.show",
        "description": "Show one orchestrator framework definition and configured profile entry if present.",
        "mutates": False,
    },
    {
        "name": "aiplane.runtimes.status",
        "description": "Show runtime/provider availability for one runtime or all configured runtimes.",
        "mutates": False,
    },
    {
        "name": "aiplane.remote.tunnel.plan",
        "description": "Render an SSH local-forwarding command for a configured remote target.",
        "mutates": False,
    },
]

WRITE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "aiplane.models.refresh",
        "description": "Import provider-discovered models into the profile catalog. Use dry_run=true to preview without writing.",
        "mutates": True,
    },
    {
        "name": "aiplane.models.use",
        "description": "Set a profile default model role to an approved model alias.",
        "mutates": True,
    },
    {
        "name": "aiplane.hardware.use",
        "description": "Select a hardware template and optional overrides in the active profile.",
        "mutates": True,
    },
    {
        "name": "aiplane.runtimes.use",
        "description": "Set the preferred runtime for a configured model.",
        "mutates": True,
    },
    {
        "name": "aiplane.remote.tunnel.start",
        "description": "Start a configured SSH tunnel in the background.",
        "mutates": True,
    },
    {
        "name": "aiplane.remote.tunnel.stop",
        "description": "Stop a helper-started SSH tunnel.",
        "mutates": True,
    },
    {
        "name": "aiplane.remote.tunnel.status",
        "description": "Show helper-started SSH tunnel status.",
        "mutates": False,
    },
]


MUTATING_TOOL_NAMES = {str(tool["name"]) for tool in WRITE_TOOLS if tool.get("mutates")}
_WRITE_CONFIRM_PROPERTY = {
    "type": "boolean",
    "default": False,
    "description": "Explicitly confirm this individual mutation; the server must also be started with --allow-writes.",
}


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "aiplane.docs.list": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "aiplane.docs.read": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "start": {"type": "integer", "minimum": 0, "default": 0},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": 50000, "default": 12000},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "aiplane.profiles.list": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "aiplane.providers.list": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["enabled", "disabled", "all"],
                "default": "all",
            },
            "group_by": {
                "type": "string",
                "enum": ["runtime", "ownership"],
            },
            "runtime": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    },
    "aiplane.providers.models": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "provider": {"type": "string"},
        },
        "required": ["provider"],
        "additionalProperties": False,
    },
    "aiplane.models.defaults": {
        "type": "object",
        "properties": {"profile": {"type": "string"}},
        "additionalProperties": False,
    },
    "aiplane.models.list": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            **MODEL_FILTER_SCHEMA_PROPERTIES,
            "sort_by": {
                "type": "string",
                "enum": MODEL_SORT_CHOICES,
                "default": "name",
            },
            "limit": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "aiplane.models.show": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "model": {"type": "string"},
        },
        "required": ["model"],
        "additionalProperties": False,
    },
    "aiplane.hardware.discover": {
        "type": "object",
        "properties": {"profile": {"type": "string"}},
        "additionalProperties": False,
    },
    "aiplane.hardware.recommend": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "include_not_recommended": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
    "aiplane.machines.list": {
        "type": "object",
        "properties": {"profile": {"type": "string"}},
        "additionalProperties": False,
    },
    "aiplane.machines.show": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "aiplane.machines.recommend": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "model": {"type": "string"},
            "runtime": {"type": "string"},
            "workload": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "aiplane.stacks.list": {
        "type": "object",
        "properties": {"profile": {"type": "string"}},
        "additionalProperties": False,
    },
    "aiplane.stacks.show": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "aiplane.stacks.plan": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "aiplane.stacks.doctor": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "aiplane.stacks.export": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "artifact": {
                "type": "string",
                "enum": [
                    "continue",
                    "openai-compatible",
                    "dockerfile",
                    "conda-yaml",
                    "compose",
                    "langgraph",
                    "crewai",
                    "autogen",
                    "semantic-kernel",
                    "llamaindex-workflows",
                    "openhands",
                ],
            },
            "name": {"type": "string"},
        },
        "required": ["artifact", "name"],
        "additionalProperties": False,
    },
    "aiplane.integrations.export": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "tool": {
                "type": "string",
                "enum": ALL_INTEGRATION_TOOLS,
            },
            "model": {"type": "string"},
            "endpoint": {"type": "string"},
            "api_key_env": {"type": "string"},
        },
        "required": ["tool"],
        "additionalProperties": False,
    },
    "aiplane.integrations.roles": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "tool": {"type": "string", "enum": ALL_INTEGRATION_TOOLS},
        },
        "required": ["tool"],
        "additionalProperties": False,
    },
    "aiplane.integrations.plan": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "tool": {"type": "string", "enum": ALL_INTEGRATION_TOOLS},
            "model": {"type": "string"},
            "provider": {"type": "string"},
            "runtime": {"type": "string"},
            "capability": {"type": "array", "items": {"type": "string"}},
            "select_best": {"type": "boolean", "default": False},
            "chat": {"type": "string"},
            "autocomplete": {"type": "string"},
            "embedding": {"type": "string"},
            "endpoint": {"type": "string"},
            "api_key_env": {"type": "string"},
        },
        "required": ["tool"],
        "additionalProperties": False,
    },
    "aiplane.orchestrators.list": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "provider": {"type": "array", "items": {"type": "string"}},
            "runtime": {"type": "array", "items": {"type": "string"}},
            "group_by": {"type": "string", "enum": ["provider", "runtime", "pattern"]},
        },
        "additionalProperties": False,
    },
    "aiplane.orchestrators.show": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    "aiplane.runtimes.status": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "runtime": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "aiplane.remote.tunnel.plan": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "target": {"type": "string"},
        },
        "required": ["target"],
        "additionalProperties": False,
    },
    "aiplane.models.refresh": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "provider": {"type": "string", "default": "all"},
            "disable_new": {"type": "boolean", "default": False},
            "include_empty_providers": {"type": "boolean", "default": False},
            "dry_run": {"type": "boolean", "default": False},
            "verbosity": {"type": "integer", "enum": [0, 1, 2], "default": 0},
        },
        "additionalProperties": False,
    },
    "aiplane.models.use": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "role": {"type": "string"},
            "model": {"type": "string"},
        },
        "required": ["role", "model"],
        "additionalProperties": False,
    },
    "aiplane.hardware.use": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "template": {"type": "string"},
            "set": {"type": "object", "additionalProperties": True},
        },
        "required": ["template"],
        "additionalProperties": False,
    },
    "aiplane.runtimes.use": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "model": {"type": "string"},
            "runtime": {"type": "string"},
        },
        "required": ["model", "runtime"],
        "additionalProperties": False,
    },
    "aiplane.remote.tunnel.start": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "target": {"type": "string"},
        },
        "required": ["target"],
        "additionalProperties": False,
    },
    "aiplane.remote.tunnel.stop": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "target": {"type": "string"},
        },
        "required": ["target"],
        "additionalProperties": False,
    },
    "aiplane.remote.tunnel.status": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "target": {"type": "string"},
        },
        "required": ["target"],
        "additionalProperties": False,
    },
}


for _mutating_tool_name in MUTATING_TOOL_NAMES:
    TOOL_SCHEMAS[_mutating_tool_name]["properties"]["confirm"] = dict(_WRITE_CONFIRM_PROPERTY)


def mcp_manifest() -> dict[str, Any]:
    return {
        "name": "aiplane-mcp",
        "status": "guarded_write_stdio_available",
        "transport": "stdio",
        "policy": "The MCP server is read-only by default. Mutations require operator startup with --allow-writes plus confirm=true on each call, then execute through existing managers and local audit.",
        "tools": READ_ONLY_TOOLS + WRITE_TOOLS,
        "write_tools": WRITE_TOOLS,
        "deferred_write_tools": [
            "aiplane.models.pull",
            "aiplane.models.benchmark",
            "aiplane.deploy.plan",
        ],
        "blocked_until_guarded": [
            "aiplane.deploy.apply",
            "arbitrary shell execution",
            "secret writes",
        ],
    }


class AiplaneMcpServer:
    def __init__(
        self,
        workspace,
        default_profile: str | None = None,
        profiles_dir=None,
        *,
        allow_writes: bool = False,
    ):
        self.workspace = workspace
        self.default_profile = default_profile
        self.profiles_dir = profiles_dir
        self.allow_writes = allow_writes

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        try:
            if method == "initialize":
                return _result(request_id, self._initialize_result())
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return _result(request_id, {})
            if method == "tools/list":
                return _result(request_id, {"tools": self._tools()})
            if method == "tools/call":
                params = _dict(message.get("params"))
                name = str(params.get("name") or "")
                arguments = _dict(params.get("arguments"))
                return _result(request_id, _tool_content(self.call_tool(name, arguments)))
            if request_id is None:
                return None
            return _error(request_id, -32601, f"method not found: {method}")
        except Exception as exc:  # noqa: BLE001 - JSON-RPC errors should be returned to the client.
            if request_id is None:
                return None
            return _error(request_id, -32000, f"{type(exc).__name__}: operation failed; see local audit log")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "aiplane.docs.list":
            return {"docs": self._doc_index()}
        if name == "aiplane.docs.read":
            return self._read_doc(
                str(arguments.get("path") or ""),
                start=int(arguments.get("start") or 0),
                max_chars=int(arguments.get("max_chars") or 12000),
            )
        if name == "aiplane.profiles.list":
            return {"profiles": list_profiles(self.profiles_dir)}

        profile_name = resolve_profile_name(
            str(arguments.get("profile") or self.default_profile or "") or None,
            profiles_dir=self.profiles_dir,
        )
        profile = load_profile(profile_name, self.workspace, profiles_dir=self.profiles_dir)

        mutates = _call_mutates(name, arguments)
        if mutates and not self.allow_writes:
            self._audit(profile, name, "blocked", {"reason": "server_read_only"})
            raise PermissionError(
                "MCP writes are disabled; restart with --allow-writes and confirm the individual call"
            )
        if mutates and arguments.get("confirm") is not True:
            self._audit(profile, name, "blocked", {"reason": "confirmation_required"})
            raise PermissionError("mutating MCP calls require confirm=true")
        call_arguments = dict(arguments)
        call_arguments.pop("confirm", None)
        try:
            result = self._call_profile_tool(name, call_arguments, profile)
        except Exception as exc:
            if mutates:
                self._audit(profile, name, "failed", {"arguments": call_arguments, "error_type": type(exc).__name__})
            raise
        if mutates:
            self._audit(profile, name, "allowed", {"arguments": call_arguments})
        return result

    def _call_profile_tool(self, name: str, arguments: dict[str, Any], profile: Profile) -> Any:
        if name == "aiplane.providers.list":
            return ProviderRegistry(profile).list(
                runtimes=_string_list(arguments.get("runtime")),
                group_by=str(arguments.get("group_by") or "") or None,
                status=str(arguments.get("status") or "all"),
            )
        if name == "aiplane.providers.models":
            result = ProviderRegistry(profile).models(str(arguments.get("provider") or ""))
            return result.__dict__
        if name == "aiplane.models.defaults":
            return ModelCatalog(profile).default_summary()
        if name == "aiplane.models.list":
            catalog = ModelCatalog(profile)
            filters = model_filter_args(arguments)
            filters = merge_machine_model_filters(
                profile,
                filters,
                machine=str(arguments.get("machine") or "") or None,
                current_machine=bool(arguments.get("current_machine", False)),
            )
            rows = catalog.sort_rows(
                catalog.filter(filters),
                sort_by=str(arguments.get("sort_by") or "name"),
                roles=filters.get("roles", []),
            )
            if arguments.get("limit") is not None:
                rows = rows[: int(arguments.get("limit") or 0)]
            return {"models": rows}
        if name == "aiplane.models.show":
            return ModelCatalog(profile).show(str(arguments.get("model") or ""))
        if name == "aiplane.hardware.discover":
            return HardwareManager(profile).discover()
        if name == "aiplane.hardware.recommend":
            return HardwareManager(profile).recommend(
                include_not_recommended=bool(arguments.get("include_not_recommended", False))
            )
        if name == "aiplane.machines.list":
            return MachineManager(profile).list()
        if name == "aiplane.machines.show":
            return MachineManager(profile).show(str(arguments.get("name") or ""))
        if name == "aiplane.machines.recommend":
            return MachineManager(profile).recommend(
                model=str(arguments.get("model") or "") or None,
                runtime=str(arguments.get("runtime") or "") or None,
                workload=str(arguments.get("workload") or "") or None,
                limit=(int(arguments["limit"]) if arguments.get("limit") is not None else None),
            )
        if name == "aiplane.stacks.list":
            return StackManager(profile).list()
        if name == "aiplane.stacks.show":
            return StackManager(profile).show(str(arguments.get("name") or ""))
        if name == "aiplane.stacks.plan":
            return StackManager(profile).plan(str(arguments.get("name") or ""))
        if name == "aiplane.stacks.doctor":
            return StackManager(profile).doctor(str(arguments.get("name") or ""))
        if name == "aiplane.stacks.export":
            return StackManager(profile).export(
                str(arguments.get("artifact") or ""),
                str(arguments.get("name") or ""),
            )
        if name == "aiplane.integrations.export":
            tool = str(arguments.get("tool") or "")
            model = str(arguments.get("model") or "") or None
            endpoint = arguments.get("endpoint")
            api_key_env = arguments.get("api_key_env")
            exported = IntegrationManager(profile).export(
                tool,
                model,
                endpoint=str(endpoint) if endpoint else None,
                api_key_env=str(api_key_env) if api_key_env else None,
            )
            return {
                "tool": exported.tool,
                "model": exported.model,
                "provider": exported.provider,
                "endpoint": exported.endpoint,
                "content": exported.content,
                "notes": exported.notes,
            }
        if name == "aiplane.integrations.roles":
            return IntegrationManager(profile).roles(str(arguments.get("tool") or ""))
        if name == "aiplane.integrations.plan":
            return IntegrationManager(profile).plan(
                str(arguments.get("tool") or ""),
                model_name=str(arguments.get("model") or "") or None,
                provider=str(arguments.get("provider") or "") or None,
                runtime=str(arguments.get("runtime") or "") or None,
                capabilities=_string_list(arguments.get("capability")),
                select_best=bool(arguments.get("select_best", False)),
                chat=str(arguments.get("chat") or "") or None,
                autocomplete=str(arguments.get("autocomplete") or "") or None,
                embedding=str(arguments.get("embedding") or "") or None,
                endpoint=str(arguments.get("endpoint") or "") or None,
                api_key_env=str(arguments.get("api_key_env") or "") or None,
            )
        if name == "aiplane.orchestrators.list":
            return OrchestratorCatalog(profile).list(
                providers=_string_list(arguments.get("provider")),
                runtimes=_string_list(arguments.get("runtime")),
                group_by=str(arguments.get("group_by") or "") or None,
            )
        if name == "aiplane.orchestrators.show":
            return OrchestratorCatalog(profile).show(str(arguments.get("name") or ""))
        if name == "aiplane.runtimes.status":
            catalog = RuntimeCatalog(profile)
            runtime = arguments.get("runtime")
            runtimes = [str(runtime)] if runtime else [row["name"] for row in catalog.list()]
            return [catalog.runtime_available(item) for item in runtimes]
        if name == "aiplane.remote.tunnel.plan":
            target = str(arguments.get("target") or "")
            return RemoteManager(profile).tunnel_plan(target)
        if name == "aiplane.models.refresh":
            catalog = ModelCatalog(profile)
            provider = str(arguments.get("provider") or "all")
            write = not bool(arguments.get("dry_run", False))
            enable_new = not bool(arguments.get("disable_new", False))
            verbosity = int(arguments.get("verbosity", 0))
            if provider == "all":
                return catalog.refresh_all(
                    write=write,
                    enable=enable_new,
                    include_empty_providers=bool(arguments.get("include_empty_providers", False)),
                    verbose=verbosity >= 2,
                )
            return catalog.refresh(
                provider,
                write=write,
                enable=enable_new,
                verbose=verbosity >= 2,
            )
        if name == "aiplane.models.use":
            return ModelCatalog(profile).set_default(
                str(arguments.get("role") or ""), str(arguments.get("model") or "")
            )
        if name == "aiplane.hardware.use":
            overrides = _dict(arguments.get("set"))
            return HardwareManager(profile).use_template(str(arguments.get("template") or ""), overrides)
        if name == "aiplane.runtimes.use":
            return RuntimeCatalog(profile).set_preferred_runtime(
                str(arguments.get("model") or ""), str(arguments.get("runtime") or "")
            )
        if name == "aiplane.remote.tunnel.status":
            return RemoteManager(profile).tunnel_status(str(arguments.get("target") or ""))
        if name == "aiplane.remote.tunnel.start":
            return RemoteManager(profile).tunnel_start(str(arguments.get("target") or ""), yes=True)
        if name == "aiplane.remote.tunnel.stop":
            return RemoteManager(profile).tunnel_stop(str(arguments.get("target") or ""), yes=True)

        raise ValueError(f"unknown MCP tool: {name}")

    def _audit(self, profile: Profile, name: str, decision: str, details: dict[str, Any]) -> None:
        AuditLogger(profile).record(AuditEvent("mcp", profile.name, name, decision, details))

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "aiplane-mcp", "version": "0.1.0"},
            "capabilities": {"tools": {}},
        }

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": TOOL_SCHEMAS[tool["name"]],
            }
            for tool in READ_ONLY_TOOLS + WRITE_TOOLS
        ]

    def _doc_index(self) -> list[dict[str, Any]]:
        root = FsPath(self.workspace).resolve()
        docs: list[dict[str, Any]] = []
        for rel in _allowed_doc_paths(root):
            path = root / rel
            title = rel
            try:
                first = path.read_text(encoding="utf-8", errors="replace").splitlines()
                heading = next((line.strip("# ").strip() for line in first if line.startswith("#")), "")
                if heading:
                    title = heading
            except OSError:
                continue
            docs.append({"path": rel, "title": title})
        return docs

    def _read_doc(self, path: str, start: int, max_chars: int) -> dict[str, Any]:
        root = FsPath(self.workspace).resolve()
        allowed = set(_allowed_doc_paths(root))
        rel = path.strip()
        if rel not in allowed:
            raise ValueError("unknown doc path; call aiplane.docs.list first")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("doc path escapes workspace") from exc
        text = target.read_text(encoding="utf-8", errors="replace")
        safe_start = max(0, int(start))
        safe_max = max(1, min(int(max_chars), 50000))
        chunk = text[safe_start : safe_start + safe_max]
        return {
            "path": rel,
            "start": safe_start,
            "max_chars": safe_max,
            "total_chars": len(text),
            "truncated": (safe_start + safe_max) < len(text),
            "content": chunk,
        }


def _call_mutates(name: str, arguments: dict[str, Any]) -> bool:
    if name == "aiplane.models.refresh" and bool(arguments.get("dry_run", False)):
        return False
    return name in MUTATING_TOOL_NAMES


def serve_stdio(
    workspace,
    default_profile: str | None = None,
    profiles_dir=None,
    *,
    allow_writes: bool = False,
) -> int:
    server = AiplaneMcpServer(
        workspace,
        default_profile=default_profile,
        profiles_dir=profiles_dir,
        allow_writes=allow_writes,
    )
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return 0
        response = server.handle_message(message)
        if response is not None:
            _write_message(sys.stdout.buffer, response)


def _read_message(stream) -> dict[str, Any] | None:
    content_length = None
    while True:
        line = stream.readline()
        if line == b"":
            return None
        if line in {b"\r\n", b"\n"}:
            break
        header = line.decode("ascii", errors="replace").strip()
        key, _, value = header.partition(":")
        if key.lower() == "content-length":
            content_length = int(value.strip())
    if content_length is None:
        raise ValueError("missing Content-Length header")
    body = stream.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(stream, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_content(value: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json_dumps(value, indent=2),
            }
        ],
        "structuredContent": value,
    }


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _allowed_doc_paths(workspace: FsPath) -> list[str]:
    roots = [
        workspace / "docs" / "user",
        workspace / "docs" / "project",
    ]
    paths: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.rglob("*.md")):
            if item.is_file():
                paths.append(str(item.relative_to(workspace)))
    for single in [workspace / "README.md", workspace / "skills" / "aiplane" / "SKILL.md"]:
        if single.is_file():
            paths.append(str(single.relative_to(workspace)))
    # Deduplicate while preserving deterministic order.
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered
