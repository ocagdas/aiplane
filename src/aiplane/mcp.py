from __future__ import annotations

import json
import sys
from typing import Any

from .audit import AuditLogger
from .config import list_profiles, load_profile, resolve_profile_name
from .hardware import HardwareManager
from .integrations import IntegrationManager
from .model_catalog import ModelCatalog
from .runtime_catalog import RuntimeCatalog
from .model_filters import MODEL_FILTER_SCHEMA_PROPERTIES, MODEL_SORT_CHOICES, model_filter_args
from .output import json_dumps
from .providers import ProviderRegistry
from .remote import RemoteManager
from .models import AuditEvent, Profile


READ_ONLY_TOOLS: list[dict[str, Any]] = [
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
        "name": "aiplane.integrations.export",
        "description": "Generate IDE/CLI config snippets for a selected model endpoint.",
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


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
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
            "sort_by": {"type": "string", "enum": MODEL_SORT_CHOICES, "default": "name"},
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
    "aiplane.integrations.export": {
        "type": "object",
        "properties": {
            "profile": {"type": "string"},
            "tool": {
                "type": "string",
                "enum": [
                    "continue",
                    "cline",
                    "zed",
                    "aider",
                    "openai-compatible",
                    "vscode-mcp",
                    "continue-mcp",
                    "cline-mcp",
                    "generic-mcp",
                ],
            },
            "model": {"type": "string"},
            "endpoint": {"type": "string"},
            "api_key_env": {"type": "string"},
        },
        "required": ["tool"],
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
            "verbose": {"type": "boolean", "default": False},
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


def mcp_manifest() -> dict[str, Any]:
    return {
        "name": "aiplane-mcp",
        "status": "guarded_write_stdio_available",
        "transport": "stdio",
        "policy": "MCP tools must call existing aiplane managers and must not bypass policy/audit checks. Mutating tools execute through the same managers as the CLI.",
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
    def __init__(self, workspace, default_profile: str | None = None, profiles_dir=None):
        self.workspace = workspace
        self.default_profile = default_profile
        self.profiles_dir = profiles_dir

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
            return _error(request_id, -32000, str(exc))

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "aiplane.profiles.list":
            return {"profiles": list_profiles(self.profiles_dir)}

        profile_name = resolve_profile_name(
            str(arguments.get("profile") or self.default_profile or "") or None,
            profiles_dir=self.profiles_dir,
        )
        profile = load_profile(profile_name, self.workspace, profiles_dir=self.profiles_dir)

        mutates = name in MUTATING_TOOL_NAMES
        try:
            result = self._call_profile_tool(name, arguments, profile)
        except Exception as exc:
            if mutates:
                self._audit(profile, name, "failed", {"arguments": arguments, "error": str(exc)})
            raise
        if mutates:
            self._audit(profile, name, "allowed", {"arguments": arguments})
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
            if provider == "all":
                return catalog.refresh_all(
                    write=write,
                    enable=enable_new,
                    include_empty_providers=bool(arguments.get("include_empty_providers", False)),
                    verbose=bool(arguments.get("verbose", False)),
                )
            return catalog.refresh(
                provider,
                write=write,
                enable=enable_new,
                verbose=bool(arguments.get("verbose", False)),
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


def serve_stdio(workspace, default_profile: str | None = None, profiles_dir=None) -> int:
    server = AiplaneMcpServer(workspace, default_profile=default_profile, profiles_dir=profiles_dir)
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
