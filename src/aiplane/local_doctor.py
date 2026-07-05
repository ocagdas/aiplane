from __future__ import annotations

from typing import Any

from .config import CONFIG_FILES
from .hardware import HardwareManager
from .integration_contracts import required_roles
from .model_catalog import ModelCatalog, ownership_for_model
from .models import Profile
from .mcp import mcp_manifest
from .tools import ToolchainManager

LOCAL_CODING_DEFAULT_ROLES = {
    "chat": "chat_model",
    "autocomplete": "autocomplete_model",
    "embedding": "embedding_model",
    "code": "code_model",
}

LOCAL_CODING_MCP_TOOLS = {
    "aiplane.profiles.list",
    "aiplane.providers.list",
    "aiplane.models.defaults",
    "aiplane.models.list",
    "aiplane.hardware.recommend",
    "aiplane.integrations.roles",
    "aiplane.integrations.plan",
    "aiplane.integrations.export",
    "aiplane.runtimes.status",
    "aiplane.remote.tunnel.plan",
}


def local_coding_doctor(profile: Profile, include_optional: bool = False) -> dict[str, Any]:
    catalog = ModelCatalog(profile)
    providers = catalog.providers()
    models = catalog.models()
    defaults = catalog.defaults()
    model_statuses = {status.name: status for status in catalog.doctor()}
    sections = [
        _profile_section(profile),
        _environment_section(profile, include_optional=include_optional),
        _model_defaults_section(catalog, models, defaults, model_statuses, providers),
        _endpoint_section(models, defaults, model_statuses, providers),
        _hardware_section(profile, models, defaults),
        _provider_section(providers),
        _integration_section(defaults, models),
        _mcp_section(),
    ]
    blocking = sum(1 for section in sections for check in section["checks"] if not check.get("ok"))
    warnings = sum(1 for section in sections for check in section["checks"] if check.get("warning"))
    return {
        "name": "local_coding_doctor",
        "profile": profile.name,
        "ok": blocking == 0,
        "summary": {
            "sections": len(sections),
            "checks": sum(len(section["checks"]) for section in sections),
            "blocking": blocking,
            "warnings": warnings,
        },
        "sections": sections,
        "next_steps": _next_steps(profile.name, sections),
        "notes": [
            "This command is read-only and local/hybrid AI coding stack focused.",
            "It aggregates existing profile, environment, model, integration, and MCP checks; it does not install runtimes, pull models, or edit IDE configuration.",
        ],
    }


def local_coding_doctor_text(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    lines = [
        f"aiplane doctor for profile {payload.get('profile', 'unknown')}",
        f"status: {'ok' if payload.get('ok') else 'needs attention'}; checks: {summary.get('checks', 0)}; blocking: {summary.get('blocking', 0)}; warnings: {summary.get('warnings', 0)}",
        "",
    ]
    sections = payload.get("sections", [])
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict):
            continue
        marker = "ok" if section.get("ok") else "needs attention"
        lines.append(f"{section.get('name', 'section')}: {marker}")
        checks = section.get("checks", [])
        for check in checks if isinstance(checks, list) else []:
            if not isinstance(check, dict):
                continue
            status = "ok" if check.get("ok") else "missing"
            if check.get("warning"):
                status = "warn"
            detail = str(check.get("detail") or check.get("reason") or "")
            suffix = f" - {detail}" if detail else ""
            lines.append(f"  - {check.get('name')}: {status}{suffix}")
        lines.append("")
    next_steps = payload.get("next_steps", [])
    if isinstance(next_steps, list) and next_steps:
        lines.append("next steps:")
        lines.extend(f"- {step}" for step in next_steps)
    return "\n".join(lines).rstrip()


def _profile_section(profile: Profile) -> dict[str, Any]:
    checks = [
        {
            "name": f"file:{filename}",
            "ok": (profile.root / filename).exists(),
            "detail": str(profile.root / filename),
        }
        for filename in CONFIG_FILES.values()
    ]
    active = profile.environment.get("active") if isinstance(profile.environment, dict) else None
    modes = profile.environment.get("modes", {}) if isinstance(profile.environment, dict) else {}
    checks.append(
        {
            "name": "environment:active_mode",
            "ok": isinstance(modes, dict) and active in modes,
            "detail": str(active or ""),
        }
    )
    return {
        "name": "profile",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _environment_section(profile: Profile, include_optional: bool) -> dict[str, Any]:
    doctor = ToolchainManager(profile).environment_doctor(include_optional=include_optional)
    summary = doctor.get("summary", {}) if isinstance(doctor.get("summary"), dict) else {}
    missing_tools = int(summary.get("tools_missing_installable_by_aiplane", 0)) + int(
        summary.get("tools_missing_manual_or_platform_specific", 0)
    )
    missing_runtime = int(summary.get("runtime_prerequisites_missing", 0))
    checks = [
        {
            "name": "required_tools",
            "ok": missing_tools == 0,
            "detail": f"{summary.get('tools_installed', 0)}/{summary.get('tools_checked', 0)} installed",
        },
        {
            "name": "runtime_prerequisites",
            "ok": missing_runtime == 0,
            "detail": f"{missing_runtime} missing",
        },
    ]
    return {
        "name": "environment",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "summary": summary,
    }


def _model_defaults_section(
    catalog: ModelCatalog,
    models: dict[str, dict[str, Any]],
    defaults: dict[str, Any],
    statuses: dict[str, Any],
    providers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checks = []
    for label, default_role in LOCAL_CODING_DEFAULT_ROLES.items():
        alias = defaults.get(default_role)
        model = models.get(str(alias)) if alias else None
        status = statuses.get(str(alias)) if alias else None
        capability_ok, capability_reason = _role_capability(default_role, model)
        provider_name = str(model.get("provider") or "") if isinstance(model, dict) else ""
        provider = providers.get(provider_name, {})
        endpoint = _provider_endpoint(provider_name, provider)
        ownership = ownership_for_model(model, provider) if isinstance(model, dict) else None
        configured = bool(alias and isinstance(model, dict) and bool(model.get("enabled", True)))
        checks.append(
            {
                "name": default_role,
                "ok": bool(configured and capability_ok),
                "detail": _default_detail(str(alias or "not configured"), provider_name, endpoint),
                "reason": (capability_reason if configured and not capability_ok else _status_reason(status)),
                "provider": provider_name or (status.provider if status else None),
                "endpoint": endpoint,
                "ownership": ownership,
                "runtime": (
                    model.get("preferred_runtime") or model.get("runtime") if isinstance(model, dict) else None
                ),
                "model": model.get("model") if isinstance(model, dict) else None,
                "roles": model.get("roles", []) if isinstance(model, dict) else [],
                "usable": (status.usable if status else False),
                "warning": bool(configured and capability_ok and status and not status.usable),
                "role": label,
            }
        )
    configured_models = len(catalog.models())
    checks.append(
        {
            "name": "model_catalog",
            "ok": configured_models > 0,
            "detail": f"{configured_models} configured/discovered aliases",
        }
    )
    return {
        "name": "model_defaults",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _endpoint_section(
    models: dict[str, dict[str, Any]],
    defaults: dict[str, Any],
    statuses: dict[str, Any],
    providers: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    aliases = _configured_default_aliases(defaults, models)
    checks.append(
        {
            "name": "role_default_endpoints",
            "ok": bool(aliases),
            "detail": (
                f"{len(aliases)} configured role default endpoint aliases"
                if aliases
                else "no configured role default aliases"
            ),
        }
    )
    for role, alias, model in aliases:
        provider_name = str(model.get("provider") or "")
        provider = providers.get(provider_name, {})
        endpoint = _provider_endpoint(provider_name, provider)
        status = statuses.get(alias)
        provider_enabled = bool(provider.get("enabled", True))
        checks.append(
            {
                "name": f"endpoint:{role}",
                "ok": bool(provider_enabled and endpoint and status and status.usable),
                "detail": _endpoint_detail(alias, provider_name, endpoint),
                "reason": _status_reason(status),
                "alias": alias,
                "provider": provider_name or None,
                "endpoint": endpoint,
                "provider_enabled": provider_enabled,
                "model": model.get("model"),
            }
        )
    return {
        "name": "endpoints",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _hardware_section(profile: Profile, models: dict[str, dict[str, Any]], defaults: dict[str, Any]) -> dict[str, Any]:
    manager = HardwareManager(profile)
    active = manager.active_config()
    machine = active.get("machine") if isinstance(active.get("machine"), dict) else {}
    checks: list[dict[str, Any]] = [
        {
            "name": "active_machine",
            "ok": bool(machine),
            "detail": (_machine_detail(machine) if machine else "no effective machine profile"),
        }
    ]
    seen_aliases: set[str] = set()
    for role, default_role in LOCAL_CODING_DEFAULT_ROLES.items():
        alias = defaults.get(default_role)
        if not alias or str(alias) in seen_aliases:
            continue
        seen_aliases.add(str(alias))
        model = models.get(str(alias))
        if not isinstance(model, dict):
            continue
        fit = manager.check_model_fit({"name": str(alias), **model})
        checks.append(
            {
                "name": f"model_fit:{default_role}",
                "ok": bool(fit.usable),
                "detail": f"{alias}: {fit.reason}",
                "model": fit.model,
                "alias": str(alias),
                "role": role,
                "warning": bool(fit.usable and "below recommended" in fit.reason),
            }
        )
    return {
        "name": "hardware",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _provider_section(providers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enabled = [name for name, provider in providers.items() if bool(provider.get("enabled", True))]
    checks = [
        {
            "name": "providers_configured",
            "ok": bool(providers),
            "detail": f"{len(providers)} known providers",
        },
        {
            "name": "providers_enabled",
            "ok": bool(enabled),
            "detail": f"{len(enabled)} enabled providers",
        },
    ]
    return {
        "name": "providers",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _integration_section(defaults: dict[str, Any], models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checks = []
    role_defaults = {
        "chat": "chat_model",
        "autocomplete": "autocomplete_model",
        "embedding": "embedding_model",
    }
    for tool in ["continue", "aider"]:
        gaps = []
        role_aliases: dict[str, str] = {}
        for role in required_roles(tool):
            role_name = role["name"]
            default_role = role_defaults.get(role_name, "chat_model")
            alias = defaults.get(default_role)
            role_aliases[role_name] = str(alias or "")
            model = models.get(str(alias)) if alias else None
            capability_ok, reason = _role_capability(default_role, model)
            if not alias or not isinstance(model, dict):
                gaps.append(f"{role_name}:missing")
            elif not capability_ok:
                gaps.append(f"{role_name}:incompatible ({reason})")
        checks.append(
            {
                "name": f"integration:{tool}",
                "ok": not gaps,
                "detail": "ready" if not gaps else "role gaps: " + ", ".join(gaps),
                "role_aliases": role_aliases,
            }
        )
    return {
        "name": "integrations",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _mcp_section() -> dict[str, Any]:
    manifest = mcp_manifest()
    tools = manifest.get("tools", []) if isinstance(manifest, dict) else []
    tool_names = {str(tool.get("name")) for tool in tools if isinstance(tool, dict) and tool.get("name")}
    missing_wedge_tools = sorted(LOCAL_CODING_MCP_TOOLS - tool_names)
    guarded_writes = sorted(name for name in tool_names if name in _guarded_mcp_write_tools())
    checks = [
        {
            "name": "mcp_manifest",
            "ok": bool(tools),
            "detail": f"{len(tools) if isinstance(tools, list) else 0} tools advertised",
        },
        {
            "name": "mcp_local_coding_read_surface",
            "ok": not missing_wedge_tools,
            "detail": ("ready" if not missing_wedge_tools else "missing tools: " + ", ".join(missing_wedge_tools)),
            "required_tools": sorted(LOCAL_CODING_MCP_TOOLS),
            "missing_tools": missing_wedge_tools,
        },
        {
            "name": "mcp_guarded_write_surface",
            "ok": True,
            "detail": f"{len(guarded_writes)} narrow audited write/lifecycle tools advertised",
            "tools": guarded_writes,
            "note": "Broad runtime installs, model pulls, cloud apply, secret writes, and arbitrary shell execution remain outside this MCP readiness check.",
        },
    ]
    return {"name": "mcp", "ok": all(check["ok"] for check in checks), "checks": checks}


def _guarded_mcp_write_tools() -> set[str]:
    return {
        "aiplane.models.refresh",
        "aiplane.models.use",
        "aiplane.hardware.use",
        "aiplane.runtimes.use",
        "aiplane.remote.tunnel.start",
        "aiplane.remote.tunnel.stop",
        "aiplane.remote.tunnel.status",
    }


def _configured_default_aliases(
    defaults: dict[str, Any], models: dict[str, dict[str, Any]]
) -> list[tuple[str, str, dict[str, Any]]]:
    aliases: list[tuple[str, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for role, default_role in LOCAL_CODING_DEFAULT_ROLES.items():
        alias = defaults.get(default_role)
        if not alias or str(alias) in seen:
            continue
        model = models.get(str(alias))
        if not isinstance(model, dict):
            continue
        aliases.append((role, str(alias), model))
        seen.add(str(alias))
    return aliases


def _role_capability(default_role: str, model: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(model, dict):
        return False, "missing profile-owned or discovered model alias"
    roles = {str(role) for role in model.get("roles", []) or []}
    scores = model.get("capability_scores") if isinstance(model.get("capability_scores"), dict) else {}
    positive_scores = {name for name, value in scores.items() if _positive_score(value)}
    allowed_roles = {
        "chat_model": {"chat", "generation"},
        "autocomplete_model": {"completion", "autocomplete", "code", "chat"},
        "embedding_model": {"embedding"},
        "code_model": {"completion", "generation", "refactor", "code", "chat"},
    }.get(default_role, {"chat", "generation"})
    allowed_scores = {
        "chat_model": {"general_chat", "reasoning", "tool_use"},
        "autocomplete_model": {"code_completion", "code_generation", "general_chat"},
        "embedding_model": {"embedding"},
        "code_model": {"code_generation", "debugging_refactor", "general_chat"},
    }.get(default_role, {"general_chat"})
    if roles.intersection(allowed_roles) or positive_scores.intersection(allowed_scores):
        return True, "role capability is compatible"
    role_text = ", ".join(sorted(roles)) or "none"
    return False, f"alias roles are not suitable for {default_role}: roles={role_text}"


def _positive_score(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _status_reason(status: Any) -> str:
    return status.reason if status else "missing profile-owned or discovered model alias"


def _provider_endpoint(provider_name: str, provider: dict[str, Any]) -> str | None:
    endpoint = provider.get("endpoint")
    if endpoint:
        return str(endpoint)
    if provider_name == "openai":
        return "https://api.openai.com/v1"
    if provider_name == "anthropic":
        return "https://api.anthropic.com"
    if provider_name == "ollama":
        return "http://localhost:11434"
    return None


def _endpoint_detail(alias: str, provider: str, endpoint: str | None) -> str:
    if endpoint:
        return f"{alias}; provider={provider or 'unknown'}; endpoint={endpoint}"
    return f"{alias}; provider={provider or 'unknown'}; endpoint not configured"


def _default_detail(alias: str, provider: str, endpoint: str | None) -> str:
    parts = [alias]
    if provider:
        parts.append(f"provider={provider}")
    if endpoint:
        parts.append(f"endpoint={endpoint}")
    return "; ".join(parts)


def _machine_detail(machine: dict[str, Any]) -> str:
    memory = machine.get("memory_gb")
    gpu = machine.get("gpu_model") or machine.get("gpu_vendor")
    vram = machine.get("total_vram_gb") or machine.get("vram_gb")
    parts = []
    if memory is not None:
        parts.append(f"RAM={memory}GB")
    if gpu:
        parts.append(f"GPU={gpu}")
    if vram is not None:
        parts.append(f"VRAM={vram}GB")
    return ", ".join(parts) or str(machine.get("machine_tag") or machine.get("provider") or "configured")


def _next_steps(profile: str, sections: list[dict[str, Any]]) -> list[str]:
    section_ok = {section["name"]: bool(section.get("ok")) for section in sections}
    steps = []
    if not section_ok.get("profile", False):
        steps.append(f"Run `aiplane profiles validate {profile}` and repair missing profile files before setup.")
    if not section_ok.get("environment", False):
        steps.append(
            "Run `aiplane environment doctor --required-only` and fix required tool/runtime prerequisites first."
        )
    if not section_ok.get("model_defaults", False):
        steps.append(
            "Run `aiplane models refresh --dry-run`, then promote/add reviewed aliases and set chat/autocomplete/embedding defaults."
        )
    if not section_ok.get("endpoints", False):
        steps.append(
            "Run `aiplane runtimes status <runtime>` or `aiplane providers test <provider>` for endpoint-specific diagnostics."
        )
    if not section_ok.get("hardware", False):
        steps.append("Run `aiplane hardware doctor` or choose a smaller local model alias for this machine.")
    if not section_ok.get("integrations", False):
        steps.append(
            "Run `aiplane integrations roles continue` and `aiplane integrations plan continue` after model defaults are configured."
        )
    if section_ok.get("integrations", False):
        steps.append(
            "Export configs with `aiplane integrations export continue` and `aiplane integrations export aider`."
        )
    steps.append("Inspect MCP availability with `aiplane mcp manifest` when connecting IDE or agent clients.")
    return steps
