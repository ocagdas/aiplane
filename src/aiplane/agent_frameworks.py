from __future__ import annotations

from typing import Any

from .config import dump_yaml

FRAMEWORK_SPECS: dict[str, dict[str, Any]] = {
    "langgraph": {
        "packages": ["langgraph", "langchain-openai"],
        "adapter": "state_graph",
        "multi_role": True,
    },
    "crewai": {
        "packages": ["crewai"],
        "adapter": "crew",
        "multi_role": True,
    },
    "autogen": {
        "packages": ["autogen-agentchat", "autogen-ext[openai]"],
        "adapter": "team",
        "multi_role": True,
    },
    "semantic_kernel": {
        "packages": ["semantic-kernel"],
        "adapter": "kernel_agents",
        "multi_role": True,
    },
    "llamaindex_workflows": {
        "packages": ["llama-index-core", "llama-index-llms-openai-like"],
        "adapter": "workflow",
        "multi_role": True,
    },
    "openhands": {
        "packages": ["openhands-ai"],
        "adapter": "llm_config",
        "multi_role": False,
    },
    "simple-openai": {
        "packages": ["openai"],
        "adapter": "openai_client",
        "multi_role": False,
    },
}

_ALIASES = {
    "semantic-kernel": "semantic_kernel",
    "llamaindex-workflows": "llamaindex_workflows",
}


def normalize_framework(name: str) -> str:
    normalized = _ALIASES.get(str(name), str(name))
    if normalized not in FRAMEWORK_SPECS:
        raise ValueError(f"unknown agent framework: {name}")
    return normalized


def framework_readiness(framework: str, roles: dict[str, Any], approval_mode: str) -> dict[str, Any]:
    name = normalize_framework(framework)
    spec = FRAMEWORK_SPECS[name]
    checks: list[dict[str, Any]] = [
        {
            "name": "roles_present",
            "ok": bool(roles),
            "detail": f"{len(roles)} role(s)",
        },
        {
            "name": "multi_role_supported",
            "ok": bool(spec["multi_role"]) or len(roles) <= 1,
            "detail": "supported" if spec["multi_role"] else "framework starter accepts one primary role",
        },
    ]
    for role_name, role in sorted(roles.items()):
        binding = role if isinstance(role, dict) else {}
        checks.extend(
            [
                {
                    "name": f"role_model:{role_name}",
                    "ok": bool(binding.get("model_id") or binding.get("model")),
                    "detail": binding.get("model_id") or binding.get("model") or "missing",
                },
                {
                    "name": f"role_endpoint:{role_name}",
                    "ok": bool(binding.get("endpoint")),
                    "detail": binding.get("endpoint") or "missing",
                },
            ]
        )
    risky = str(approval_mode).lower() in {"auto", "none", "silent", "unattended"}
    checks.append(
        {
            "name": "approval_mode",
            "ok": not risky,
            "warning": risky,
            "detail": approval_mode,
        }
    )
    check_map = {str(check["name"]): {key: value for key, value in check.items() if key != "name"} for check in checks}
    return {
        "framework": name,
        "ready": all(bool(check["ok"]) for check in checks),
        "packages": list(spec["packages"]),
        "checks": check_map,
    }


def render_framework_starter(framework: str, metadata: dict[str, Any]) -> str:
    name = normalize_framework(framework)
    roles = metadata.get("roles") if isinstance(metadata.get("roles"), dict) else {}
    normalized_roles = {}
    for role_name, raw in sorted(roles.items()):
        role = raw if isinstance(raw, dict) else {}
        credential = role.get("credential") if isinstance(role.get("credential"), dict) else {}
        normalized_roles[str(role_name)] = {
            "model_alias": role.get("model_alias") or role.get("model"),
            "model_id": role.get("model_id") or role.get("native_model") or role.get("model"),
            "provider": role.get("provider"),
            "runtime": role.get("runtime") or metadata.get("runtime"),
            "endpoint": role.get("endpoint") or metadata.get("endpoint"),
            "api_key_env": credential.get("api_key_env") or role.get("api_key_env"),
            "tools": role.get("tools", {}),
            "limits": role.get("limits", {}),
            "approval_mode": role.get("approval_mode") or metadata.get("approval_mode") or "ask",
            "audit_label": role.get("audit_label"),
        }
    if not normalized_roles and metadata.get("model"):
        normalized_roles["primary"] = {
            "model_alias": metadata.get("model"),
            "model_id": metadata.get("model_id") or metadata.get("model"),
            "provider": metadata.get("provider"),
            "runtime": metadata.get("runtime"),
            "endpoint": metadata.get("endpoint"),
            "api_key_env": metadata.get("api_key_env"),
            "tools": metadata.get("tools", {}),
            "limits": metadata.get("limits", {}),
            "approval_mode": metadata.get("approval_mode") or "ask",
            "audit_label": metadata.get("audit_label"),
        }
    readiness = framework_readiness(name, normalized_roles, str(metadata.get("approval_mode") or "ask"))
    payload = {
        "schema_version": "1.0",
        "record_type": "agent_framework_starter",
        "render_only": True,
        "framework": name,
        "adapter": FRAMEWORK_SPECS[name]["adapter"],
        "packages": list(FRAMEWORK_SPECS[name]["packages"]),
        "stack": metadata.get("name"),
        "profile": metadata.get("profile"),
        "roles": normalized_roles,
        "topology": _topology(name, normalized_roles),
        "readiness": readiness,
        "execution_boundary": {
            "runs_agents": False,
            "installs_packages": False,
            "writes_credentials": False,
        },
        "notes": [
            "This is Aiplane starter metadata, not a claim to be the framework's native project format.",
            "Review and translate it with the selected framework version before execution.",
        ],
    }
    return dump_yaml(payload)


def _topology(framework: str, roles: dict[str, Any]) -> dict[str, Any]:
    names = list(roles)
    if framework == "langgraph":
        return {"graph": {"nodes": names, "entrypoint": names[0] if names else None, "edges": []}}
    if framework == "crewai":
        return {"crew": {"agents": names, "process": "review_required"}}
    if framework == "autogen":
        return {"team": {"participants": names, "termination": "review_required"}}
    if framework == "semantic_kernel":
        return {"kernel": {"agents": names, "selection": "review_required"}}
    if framework == "llamaindex_workflows":
        return {"workflow": {"steps": names, "transitions": []}}
    if framework == "openhands":
        return {"openhands": {"primary_role": names[0] if names else None}}
    return {"client": {"primary_role": names[0] if names else None}}
