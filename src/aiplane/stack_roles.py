from __future__ import annotations

from typing import Any

from .model_catalog import ModelCatalog
from .policy import PolicyEngine
from .runtime_catalog import RuntimeCatalog
from .runtime_definitions import PROVIDER_ENDPOINT_DEFAULTS


def _default_endpoint(runtime: str) -> str:
    from .stacks import _default_endpoint as resolve_default_endpoint

    return resolve_default_endpoint(runtime)


class StackRolePlanner:
    """Normalize, plan, and validate model-role bindings for stacks."""

    def __init__(self, profile):
        self.profile = profile

    def _normalize_roles(
        self,
        roles: dict[str, str],
        primary_model: str,
        primary_runtime: str,
        endpoint: str | None,
        limits: dict[str, object],
        tools: dict[str, object],
        approval_mode: str | None,
        audit_label: str,
    ) -> dict[str, Any]:
        if not roles:
            return {}
        catalog = ModelCatalog(self.profile)
        normalized = {}
        for role, model_alias in sorted(roles.items()):
            role_name = str(role).strip()
            if not role_name or "/" in role_name or "\\" in role_name:
                raise ValueError("role names must be simple names")
            alias = str(model_alias).strip()
            if not alias:
                raise ValueError(f"role {role_name!r} model alias is empty")
            model_config = catalog.show(alias)
            provider_name = str(model_config.get("provider") or model_config.get("source") or "")
            if model_config.get("ownership") == "managed_service":
                role_runtime = provider_name
                provider_config = (
                    model_config.get("provider_config") if isinstance(model_config.get("provider_config"), dict) else {}
                )
                role_endpoint = endpoint or provider_config.get("endpoint") or _default_endpoint(provider_name)
            else:
                role_runtime = model_config.get("runtime") or primary_runtime
                role_endpoint = endpoint or _default_endpoint(str(role_runtime or primary_runtime))
            normalized[role_name] = {
                "model": alias,
                "provider": provider_name,
                "ownership": model_config.get("ownership"),
                "runtime": role_runtime,
                "endpoint": role_endpoint,
                "approval_mode": approval_mode or "ask",
                "audit_label": f"{audit_label}.{role_name}",
                "limits": limits,
                "tools": tools,
                "uses_primary_model": alias == primary_model,
            }
        return normalized

    def _role_plan(self, stack: dict[str, Any], endpoint: object) -> dict[str, Any]:
        roles = stack.get("roles", {})
        if isinstance(roles, dict) and roles:
            return roles
        model = str(stack.get("model") or "")
        runtime = str(stack.get("runtime") or "")
        model_config = ModelCatalog(self.profile).show(model)
        return {
            "primary": {
                "model": model,
                "provider": model_config.get("provider") or model_config.get("source"),
                "ownership": model_config.get("ownership"),
                "runtime": runtime,
                "endpoint": str(endpoint or _default_endpoint(runtime)),
                "approval_mode": stack.get("approval_mode") or "ask",
                "audit_label": stack.get("audit_label") or "primary",
                "limits": stack.get("limits", {}),
                "tools": stack.get("tools", {}),
                "uses_primary_model": True,
            }
        }

    def _role_checks(self, roles: object) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        role_map = roles if isinstance(roles, dict) else {}
        catalog = ModelCatalog(self.profile)
        known_runtimes = {row["name"] for row in RuntimeCatalog(self.profile).list(include_gui=True)}
        known_endpoint_families = {
            name
            for name, provider in PROVIDER_ENDPOINT_DEFAULTS.items()
            if provider.get("ownership") == "managed_service"
        }
        for role, binding in sorted(role_map.items()):
            if not isinstance(binding, dict):
                checks.append(
                    {
                        "name": f"role_binding:{role}",
                        "ok": False,
                        "detail": "role binding must be a mapping",
                    }
                )
                continue
            model_alias = str(binding.get("model") or "")
            model_config: dict[str, Any] = {}
            try:
                model_config = catalog.show(model_alias)
                model_ok = True
                model_detail = model_config.get("model")
            except Exception as exc:  # noqa: BLE001 - report config health.
                model_ok = False
                model_detail = str(exc)
            checks.append(
                {
                    "name": f"role_model:{role}",
                    "ok": model_ok,
                    "detail": model_detail,
                }
            )
            if model_ok:
                policy = PolicyEngine(self.profile).model_decision(model_alias)
                checks.append(
                    {
                        "name": f"role_model_enabled:{role}",
                        "ok": bool(model_config.get("enabled", True)),
                        "detail": ("enabled" if model_config.get("enabled", True) else "disabled"),
                    }
                )
                checks.append(
                    {
                        "name": f"role_model_policy:{role}",
                        "ok": policy.allowed,
                        "detail": policy.reason,
                        "provider": str(model_config.get("provider") or ""),
                        "requires_approval": policy.requires_approval,
                    }
                )
            runtime = str(binding.get("runtime") or "")
            ownership = str(binding.get("ownership") or model_config.get("ownership") or "")
            if runtime:
                runtime_known = runtime in known_runtimes or (
                    ownership == "managed_service" and runtime in known_endpoint_families
                )
                checks.append(
                    {
                        "name": f"role_runtime_or_endpoint:{role}",
                        "ok": runtime_known,
                        "detail": runtime,
                    }
                )
            endpoint = str(binding.get("endpoint") or "")
            if ownership == "managed_service":
                checks.append(
                    {
                        "name": f"role_endpoint:{role}",
                        "ok": bool(endpoint),
                        "detail": endpoint or "managed-service role needs an endpoint",
                    }
                )
            checks.extend(self._role_tool_policy_checks(str(role), binding))
        return checks

    def _role_tool_policy_checks(self, role: str, binding: dict[str, Any]) -> list[dict[str, Any]]:
        tools = binding.get("tools") if isinstance(binding.get("tools"), dict) else {}
        approval_mode = str(binding.get("approval_mode") or "ask").lower()
        risky_approval = approval_mode in {"auto", "none", "silent", "unattended"}
        risky_tools = {
            "shell",
            "exec",
            "command",
            "filesystem",
            "network",
            "browser",
            "code_execution",
        }
        open_policies = {
            "allow",
            "allowed",
            "always",
            "auto",
            "none",
            "unrestricted",
            "write",
        }
        checks: list[dict[str, Any]] = []
        for tool, policy in sorted(tools.items()):
            tool_name = str(tool).lower()
            policy_name = str(policy).lower()
            risky = tool_name in risky_tools and (policy_name in open_policies or risky_approval)
            checks.append(
                {
                    "name": f"role_tool_policy:{role}:{tool}",
                    "ok": not risky,
                    "warning": risky,
                    "detail": (
                        "risky tool policy should use guarded/read_only/workspace_only with ask/manual approval"
                        if risky
                        else f"{policy}"
                    ),
                }
            )
        return checks
