from __future__ import annotations

from typing import Any

from .model_catalog import ROLE_CAPABILITY_MAP

MCP_EXPORT_TOOLS = {"vscode-mcp", "continue-mcp", "cline-mcp", "generic-mcp"}
ONE_MODEL_TOOLS = {"cline", "zed", "aider", "openai-compatible"}
MODEL_SELECTING_TOOLS = {"continue", *ONE_MODEL_TOOLS}
ALL_INTEGRATION_TOOLS = [
    "continue",
    "cline",
    "zed",
    "aider",
    "openai-compatible",
    "vscode-mcp",
    "continue-mcp",
    "cline-mcp",
    "generic-mcp",
]
SETUP_INTEGRATION_TOOLS = ["continue", "cline", "zed", "aider", "openai-compatible"]

INTEGRATION_DESCRIPTIONS: dict[str, str] = {
    "continue": "Print a Continue IDE/CLI config snippet for a configured model endpoint; does not install Continue",
    "cline": "Print a Cline-style OpenAI-compatible provider snippet for VS Code/CLI use",
    "zed": "Print a Zed assistant provider snippet using an OpenAI-compatible endpoint",
    "aider": "Print shell environment and command hints for Aider with an OpenAI-compatible endpoint",
    "openai-compatible": "Print a generic base_url/model/api_key_env payload for tools that accept OpenAI-compatible endpoints",
    "vscode-mcp": "Print a VS Code MCP server config that launches aiplane over stdio",
    "continue-mcp": "Print a Continue MCP server config that launches aiplane over stdio",
    "cline-mcp": "Print a Cline-style MCP server config that launches aiplane over stdio",
    "generic-mcp": "Print a generic MCP stdio server config for clients that accept mcpServers JSON",
}

INTEGRATION_ROLE_NAMES: dict[str, list[str]] = {
    "continue": ["chat", "autocomplete", "embedding"],
    "cline": ["chat"],
    "zed": ["chat"],
    "aider": ["chat"],
    "openai-compatible": ["chat"],
    "vscode-mcp": [],
    "continue-mcp": [],
    "cline-mcp": [],
    "generic-mcp": [],
}

REQUIRED_INTEGRATION_ROLES = {"chat"}


def integration_list() -> list[dict[str, str]]:
    return [{"name": name, "description": INTEGRATION_DESCRIPTIONS[name]} for name in ALL_INTEGRATION_TOOLS]


def required_roles(tool: str) -> list[dict[str, Any]]:
    if tool not in INTEGRATION_ROLE_NAMES:
        raise ValueError(f"unknown integration: {tool}")
    return [
        {
            "name": role,
            "required": role in REQUIRED_INTEGRATION_ROLES,
            "capabilities": ROLE_CAPABILITY_MAP.get(role, []),
            "filter_example": f"aiplane models list --role {role} --sort-by role --limit 3",
        }
        for role in INTEGRATION_ROLE_NAMES[tool]
    ]
