from __future__ import annotations

from typing import Any

from .config import CONFIG_FILES
from .hardware import HardwareManager
from .integration_contracts import ALL_INTEGRATION_TOOLS, required_roles
from .model_catalog import ModelCatalog, ownership_for_model
from .policy import PolicyEngine
from .models import Profile
from .mcp import mcp_manifest
from .tools import ToolchainManager
from .remote import RemoteManager
from .stacks import StackManager

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

DOCTOR_CONTRACT_VERSION = "1.0"
DOCTOR_EXIT_CODES = {
    "healthy": 0,
    "advisory": 1,
    "blocking": 2,
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
        _policy_section(profile, defaults, models),
        _remote_section(profile),
        _integration_section(defaults, models),
        _mcp_section(),
    ]
    for section in sections:
        for check in section.get("checks", []):
            if not isinstance(check, dict):
                continue
            section_name = str(section.get("name") or "general")
            check["id"] = f"{section_name}.{check.get('name', 'unknown')}"
            check["severity"], check["action"] = _section_check_status(
                str(profile.name),
                section_name,
                check,
            )
            check.setdefault("reason", check.get("detail", ""))
            check["impact"] = _check_impact(section_name, check)
            check["affected_resource"] = _affected_resource(str(profile.name), section_name, check)
            check["remediation"] = _check_remediation(
                str(profile.name),
                section_name,
                check,
                actionable=check["severity"] in {"blocking", "advisory"},
            )

    blocking = sum(
        1
        for section in sections
        for check in section.get("checks", [])
        if isinstance(check, dict) and check.get("severity") == "blocking"
    )
    advisory = sum(
        1
        for section in sections
        for check in section.get("checks", [])
        if isinstance(check, dict) and check.get("severity") == "advisory"
    )
    pass_count = sum(
        1
        for section in sections
        for check in section.get("checks", [])
        if isinstance(check, dict) and check.get("severity") == "pass"
    )
    outcome = "blocking" if blocking else "advisory" if advisory else "healthy"
    return {
        "name": "local_coding_doctor",
        "contract_version": DOCTOR_CONTRACT_VERSION,
        "profile": profile.name,
        "ok": blocking == 0,
        "outcome": outcome,
        "exit_code": DOCTOR_EXIT_CODES[outcome],
        "exit_codes": {
            "healthy": {"code": 0, "meaning": "all findings pass"},
            "advisory": {"code": 1, "meaning": "no blockers; one or more advisory findings"},
            "blocking": {"code": 2, "meaning": "one or more blocking findings"},
        },
        "summary": {
            "sections": len(sections),
            "checks": sum(len(section["checks"]) for section in sections),
            "blocking": blocking,
            "warnings": advisory,
            "checks_by_severity": {
                "blocking": blocking,
                "advisory": advisory,
                "pass": pass_count,
            },
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
        f"contract: {payload.get('contract_version', 'unversioned')}; exit_code: {payload.get('exit_code', 'unknown')}",
        f"status: {'ok' if payload.get('ok') else 'issues found'}; checks: {summary.get('checks', 0)}; needs_attention: {summary.get('blocking', 0)}; further_actions: {summary.get('warnings', 0)}",
        "",
    ]
    sections = payload.get("sections", [])

    # collect checks and warnings across sections
    blocking_items: list[tuple[str, str]] = []
    advisory_items: list[tuple[str, str]] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_name = str(section.get("name") or "general")
            for check in section.get("checks", []) or []:
                if not isinstance(check, dict):
                    continue
                reason = check.get("reason") or check.get("detail") or ""
                suggestion = str(check.get("action") or "")
                check_name = str(check.get("name") or "check")
                if section_name == "integrations" and check_name.startswith("integration:"):
                    check_name = check_name.split(":", 1)[1]
                item = f"{check_name}: {reason}"
                if suggestion:
                    item += f" -> {suggestion}"
                severity = str(
                    check.get("severity")
                    or ("blocking" if not check.get("ok") else "advisory" if check.get("warning") else "pass")
                )
                if severity == "blocking":
                    blocking_items.append((section_name, item))
                elif severity == "advisory":
                    advisory_items.append((section_name, item))

    if blocking_items:
        lines.append(f"recommended actions ({len(blocking_items)}):")
        current_root = ""
        for root, item in blocking_items:
            if root != current_root:
                lines.append(f"- {root}:")
                current_root = root
            lines.append(f"  - {item}")
        lines.append("")

    if advisory_items:
        lines.append(f"further actions/status ({len(advisory_items)}):")
        current_root = ""
        for root, item in advisory_items:
            if root != current_root:
                lines.append(f"- {root}:")
                current_root = root
            lines.append(f"  - {item}")
        lines.append("")

    # original per-section output (kept for full context)
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict):
            continue
        marker = "ok" if section.get("ok") else "needs attention"
        lines.append(f"{section.get('name')}: {marker}")
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

        provider_name = str(model.get("provider") or "") if isinstance(model, dict) else ""
        provider = providers.get(provider_name, {})
        endpoint = _provider_endpoint(provider_name, provider)
        ownership = ownership_for_model(model, provider) if isinstance(model, dict) else None

        # Treat absence of an explicit default as a non-blocking warning (informational).
        if not alias:
            ok = True
            warning = True
            reason = "not configured"
        # If an alias is present but the model isn't found in the catalog, that's a real error.
        elif not isinstance(model, dict):
            ok = False
            warning = False
            reason = f"configured alias {alias} missing from models"
        else:
            capability_ok, capability_reason = _role_capability(default_role, model)
            configured = bool(model.get("enabled", True))
            ok = bool(configured and capability_ok)
            warning = bool(configured and capability_ok and status and not status.usable)
            reason = capability_reason if configured and not capability_ok else _status_reason(status)

        checks.append(
            {
                "name": default_role,
                "ok": ok,
                "detail": _default_detail(str(alias or "not configured"), provider_name, endpoint),
                "reason": reason,
                "provider": provider_name or (status.provider if status else None),
                "endpoint": endpoint,
                "ownership": ownership,
                "runtime": (
                    model.get("preferred_runtime") or model.get("runtime") if isinstance(model, dict) else None
                ),
                "model": model.get("model") if isinstance(model, dict) else None,
                "roles": model.get("roles", []) if isinstance(model, dict) else [],
                "usable": (status.usable if status else False),
                "warning": warning,
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
    for tool in ALL_INTEGRATION_TOOLS:
        gaps = []
        role_aliases: dict[str, str] = {}
        required = required_roles(tool)
        if not required:
            checks.append(
                {
                    "name": f"integration:{tool}",
                    "ok": True,
                    "detail": "no model roles required",
                    "role_aliases": {},
                }
            )
            continue
        for role in required:
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
                "ok": True,
                "warning": bool(gaps),
                "detail": "ready" if not gaps else "role gaps: " + ", ".join(gaps),
                "role_aliases": role_aliases,
            }
        )
    return {
        "name": "integrations",
        "ok": True,
        "checks": checks,
    }


def _policy_section(profile: Profile, defaults: dict[str, Any], models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    policy = PolicyEngine(profile)
    checks = []
    checks.append(
        {
            "name": "repository_classification",
            "ok": isinstance(profile.repository, dict),
            "detail": str(profile.repository.get("classification", "private")),
        }
    )
    checks.append(
        {
            "name": "cloud_backends",
            "ok": policy.cloud_decision().allowed,
            "detail": policy.cloud_decision().reason,
            "decision": "allowed" if policy.cloud_decision().allowed else "blocked",
        }
    )

    allowed_providers = profile.repository.get("allowed_providers")
    checks.append(
        {
            "name": "allowed_providers",
            "ok": True,
            "detail": _provider_list_detail(allowed_providers),
            "allowed_providers": allowed_providers if isinstance(allowed_providers, list) else None,
        }
    )

    default_aliases = {
        name: alias for name, alias in defaults.items() if name.endswith("_model") and isinstance(alias, str) and alias
    }
    checked_aliases = sorted({str(alias) for alias in default_aliases.values() if alias})
    for alias in checked_aliases:
        model = models.get(alias)
        if not isinstance(model, dict):
            checks.append(
                {
                    "name": f"model_policy:{alias}",
                    "ok": False,
                    "detail": f"model alias missing: {alias}",
                }
            )
            continue
        decision = policy.model_decision(alias)
        checks.append(
            {
                "name": f"model_policy:{alias}",
                "ok": decision.allowed,
                "detail": decision.reason,
                "provider": str(model.get("provider") or ""),
                "model": str(model.get("model") or ""),
                "needs_approval": decision.requires_approval,
            }
        )

    return {
        "name": "policy",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }


def _provider_list_detail(allowed_providers: object) -> str:
    if not isinstance(allowed_providers, list):
        return "all providers"
    values = sorted({str(value).strip() for value in allowed_providers if str(value).strip()})
    if not values:
        return "no providers configured (default allow all)"
    return "allowed providers: " + ", ".join(values)


def _remote_section(profile: Profile) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    remote_manager = RemoteManager(profile)
    stack_manager = StackManager(profile)

    targets = profile.targets.get("targets", {})
    remote_targets = {
        name: target
        for name, target in (targets or {}).items()
        if isinstance(target, dict) and str(target.get("type") or "") == "ssh_tunnel"
    }
    target_names = sorted(remote_targets.keys())
    target_detail = (
        f"{len(target_names)} configured ssh_tunnel targets: {', '.join(target_names)}"
        if target_names
        else "0 configured ssh_tunnel targets"
    )
    checks.append(
        {
            "name": "remote_targets_configured",
            "ok": True,
            "detail": target_detail,
        }
    )

    for name in sorted(remote_targets.keys()):
        try:
            plan = remote_manager.tunnel_plan(name)
        except (ValueError, TypeError) as exc:
            checks.append(
                {
                    "name": f"remote_target:{name}",
                    "ok": False,
                    "detail": str(exc),
                    "warning": False,
                }
            )
            continue
        checks.append(
            {
                "name": f"remote_target:{name}",
                "ok": True,
                "warning": not bool(plan.get("tool_available")),
                "detail": f"endpoint={plan['endpoint']} command={plan.get('command')}",
                "required_tools": ["ssh"],
                "tool_available": bool(plan.get("tool_available")),
            }
        )

    remote_stacks = [row["name"] for row in stack_manager.list() if str(row.get("access") or "") == "ssh_tunnel"]
    remote_stack_names = sorted(remote_stacks)
    stack_detail = (
        f"{len(remote_stack_names)} stacks using ssh_tunnel access: {', '.join(remote_stack_names)}"
        if remote_stack_names
        else "0 stacks using ssh_tunnel access"
    )
    checks.append(
        {
            "name": "remote_stacks_configured",
            "ok": True,
            "detail": stack_detail,
        }
    )

    for stack_name in remote_stack_names:
        try:
            doctor = stack_manager.doctor(stack_name)
            stack_ok = bool(all(check.get("ok") for check in doctor.get("checks", [])))
            checks.append(
                {
                    "name": f"stack_doctor:{stack_name}",
                    "ok": True,
                    "warning": not stack_ok,
                    "detail": doctor.get("plan_summary", {}).get("endpoint"),
                    "reason": ("stack checks passed" if stack_ok else "stack readiness has issues"),
                }
            )
        except ValueError as exc:
            checks.append(
                {
                    "name": f"stack_doctor:{stack_name}",
                    "ok": True,
                    "warning": True,
                    "detail": str(exc),
                    "reason": "stack readiness check failed",
                }
            )

    return {
        "name": "remote",
        "ok": True,
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


def _section_check_status(profile: str, section_name: str, check: dict[str, Any]) -> tuple[str, str]:
    ok = bool(check.get("ok"))
    warning = bool(check.get("warning"))
    if not ok:
        return "blocking", _check_action(profile, section_name, check)
    if warning:
        return "advisory", _check_action(profile, section_name, check)
    return "pass", ""


def _check_impact(section: str, check: dict[str, Any]) -> str:
    name = str(check.get("name") or "")
    if section == "profile":
        return "Profile loading or validation may be incomplete."
    if section == "environment":
        return "Required local tooling or runtime prerequisites may be missing."
    if section == "model_defaults" or name == "model_catalog":
        return "Coding tools may not have usable model aliases for required roles."
    if section == "endpoints":
        return "Selected models may not be reachable by exported tools."
    if section == "hardware":
        return "Recommended local models may not fit or may run poorly on the active machine."
    if section == "providers":
        return "Model aliases may reference providers that are unavailable or disabled."
    if section == "policy":
        return "Policy may block model, provider, or cloud usage."
    if section == "integrations":
        return "Generated tool configuration may be incomplete for this integration."
    if section == "remote":
        return "Remote endpoints or workstation flows may not be reproducible."
    if section == "mcp":
        return "MCP clients may not expose the expected aiplane workflow tools."
    return "The local AI workflow may need attention before export or use."


def _check_remediation(
    profile: str,
    section: str,
    check: dict[str, Any],
    *,
    actionable: bool,
) -> dict[str, Any]:
    if not actionable:
        return {
            "command": None,
            "description": "No action required.",
            "mutation": "none",
            "mutates": False,
            "dry_run_supported": False,
            "dry_run_command": None,
        }
    action = _check_action(profile, section, check)
    command = _first_command(action) or f"aiplane doctor --profile {profile} --format json"
    command = _scope_profile(command, profile)
    dry_run_command = _dry_run_command(command)
    mutates = _command_mutates(command)
    return {
        "command": command,
        "mutates": mutates,
        "mutation": "mutating" if mutates else "read_only",
        "dry_run_supported": dry_run_command is not None,
        "dry_run_command": dry_run_command,
        "description": action,
    }


def _scope_profile(command: str, profile: str) -> str:
    if "--profile " in command or command.startswith("aiplane profiles validate "):
        return command
    return f"{command} --profile {profile}"


def _affected_resource(profile: str, section: str, check: dict[str, Any]) -> dict[str, str]:
    name = str(check.get("name") or "unknown")
    resource_name = str(
        check.get("alias")
        or check.get("provider")
        or check.get("tool")
        or (name.split(":", 1)[1] if ":" in name else name)
    )
    return {
        "profile": profile,
        "type": section,
        "name": resource_name,
    }


def _first_command(action: str) -> str | None:
    if "`" not in action:
        return None
    parts = action.split("`")
    return parts[1] if len(parts) > 1 and parts[1].strip() else None


def _dry_run_command(command: str) -> str | None:
    if "--dry-run" in command:
        return command
    dry_run_capable = (
        "aiplane models refresh",
        "aiplane hardware discover",
        "aiplane integrations setup",
        "aiplane profiles repair",
        "aiplane profiles bootstrap-local",
        "aiplane runtimes install",
        "aiplane runtimes start",
        "aiplane runtimes pull",
    )
    if command.startswith(dry_run_capable):
        return f"{command} --dry-run"
    return None


def _command_mutates(command: str) -> bool:
    mutating_prefixes = (
        "aiplane models promote",
        "aiplane models use",
        "aiplane providers enable",
        "aiplane hardware discover --select-closest",
        "aiplane profiles repair",
        "aiplane profiles bootstrap-local",
        "aiplane integrations setup",
        "aiplane runtimes install",
        "aiplane runtimes start",
        "aiplane runtimes pull",
    )
    return command.startswith(mutating_prefixes) and "--dry-run" not in command


def _check_action(profile: str, section: str, check: dict[str, Any]) -> str:
    name = str(check.get("name") or "")
    if section == "profile":
        if name.startswith("file:"):
            missing_file = name.split(":", 1)[1]
            return f"Run `aiplane profiles validate {profile}` and repair `{missing_file}`."
        return f"Run `aiplane profiles validate {profile}`."

    if section == "environment":
        if name == "required_tools":
            return "Run `aiplane environment doctor --required-only` and install missing CLIs."
        if name == "runtime_prerequisites":
            return "Run `aiplane environment doctor --required-only --include-optional` for runtime prerequisites."
        return "Run `aiplane environment doctor --required-only`."

    if section == "model_defaults" or name == "model_catalog":
        if name == "model_catalog":
            return "Run `aiplane models refresh --dry-run`, then `aiplane models list --group-by runtime` and `aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`."
        role_arg = name.removesuffix("_model") if name.endswith("_model") else "ALIAS"
        return (
            f"Run `aiplane models refresh --dry-run`; "
            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`; "
            f"`aiplane models use {role_arg} ALIAS`"
        )

    if section == "endpoints":
        if name == "role_default_endpoints":
            return f"Run `aiplane models defaults --profile {profile}`, then configure a reported role with `aiplane models use ROLE ALIAS --profile {profile}`."
        if name.startswith("endpoint:"):
            alias = str(check.get("alias") or "UNKNOWN")
            return (
                f"Run `aiplane runtimes status {str(check.get('provider') or 'runtime')}` or "
                f"`aiplane providers test {str(check.get('provider') or 'provider')}` for `{alias}`."
            )
        return "Review role default endpoint aliases in model defaults."

    if section == "hardware":
        if name == "active_machine":
            return "Run `aiplane hardware show` and `aiplane hardware discover --select-closest`."
        if name.startswith("model_fit:"):
            return "Run `aiplane hardware recommend` and choose a model that fits this machine."
        return "Run `aiplane hardware doctor` for hardware readiness checks."

    if section == "providers":
        if name == "providers_configured":
            return "Run `aiplane providers list` and add missing providers in profile provider config."
        if name == "providers_enabled":
            return f"Run `aiplane providers list --profile {profile}`, then enable one listed provider."

    if section == "integrations":
        tool = name.removeprefix("integration:")
        return f"Run `aiplane integrations roles {tool}` and `aiplane integrations plan {tool}` to fill required role gaps."

    if section == "policy":
        if name == "cloud_backends":
            return "Run `aiplane policy explain --action backend:cloud` and align repository policy before approval."
        if name == "repository_classification":
            return f"Run `aiplane policy explain --action backend:cloud --profile {profile}`, then update the reported profile policy path."
        if name.startswith("model_policy:"):
            model_alias = name.split(":", 1)[1]
            return f"Run `aiplane policy explain --action model:{model_alias}` and resolve model/provider policy constraints."
        if name == "allowed_providers":
            return "Update `allowed_providers` in the profile repository policy and re-run doctor."
        return "Run `aiplane policy explain --action backend:cloud`."

    if section == "remote":
        if name.startswith("remote_target:"):
            target = name.removeprefix("remote_target:")
            return f"Run `aiplane remote tunnel plan --target {target}` and `aiplane remote tunnel status --target {target}`."
        if name.startswith("stack_doctor:"):
            stack = name.removeprefix("stack_doctor:")
            return f"Run `aiplane stacks doctor {stack}` and address reported readiness gaps."
        return "Run `aiplane remote tunnel list` and `aiplane stacks list` to review remote access coverage."

    if section == "mcp":
        if name == "mcp_manifest":
            return "Run `aiplane mcp manifest` and check tool availability for client onboarding."
        if name == "mcp_local_coding_read_surface":
            return "Run `aiplane mcp manifest` and verify all wedge tools are available."
        if name == "mcp_guarded_write_surface":
            return (
                f"Run `aiplane mcp manifest --profile {profile}` and verify the guarded write tools and audit fields."
            )
        return "Run `aiplane mcp manifest` and validate read/write surface coverage."

    return f"Run `aiplane doctor --profile {profile} --format json` and inspect `{section}.{name}`."


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
    steps.append("Inspect integration status with `aiplane integrations list` and `aiplane integrations roles <tool>`.")
    steps.append("Export configs with `aiplane integrations export <tool>` after selecting model aliases.")
    steps.append("Inspect MCP availability with `aiplane mcp manifest` when connecting IDE or agent clients.")
    return steps
