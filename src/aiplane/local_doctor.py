from __future__ import annotations

from typing import Any

from .config import CONFIG_FILES
from .integration_contracts import required_roles
from .model_catalog import ModelCatalog
from .models import Profile
from .mcp import mcp_manifest
from .tools import ToolchainManager

LOCAL_CODING_DEFAULT_ROLES = {
    "chat": "chat_model",
    "autocomplete": "autocomplete_model",
    "embedding": "embedding_model",
    "code": "code_model",
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
        _model_defaults_section(catalog, models, defaults, model_statuses),
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
        {"name": f"file:{filename}", "ok": (profile.root / filename).exists(), "detail": str(profile.root / filename)}
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
    return {"name": "profile", "ok": all(check["ok"] for check in checks), "checks": checks}


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
    return {"name": "environment", "ok": all(check["ok"] for check in checks), "checks": checks, "summary": summary}


def _model_defaults_section(
    catalog: ModelCatalog,
    models: dict[str, dict[str, Any]],
    defaults: dict[str, Any],
    statuses: dict[str, Any],
) -> dict[str, Any]:
    checks = []
    for label, default_role in LOCAL_CODING_DEFAULT_ROLES.items():
        alias = defaults.get(default_role)
        model = models.get(str(alias)) if alias else None
        status = statuses.get(str(alias)) if alias else None
        checks.append(
            {
                "name": default_role,
                "ok": bool(alias and isinstance(model, dict) and bool(model.get("enabled", True))),
                "detail": str(alias or "not configured"),
                "reason": (status.reason if status else "missing profile-owned or discovered model alias"),
                "provider": (status.provider if status else None),
                "usable": (status.usable if status else False),
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
    return {"name": "model_defaults", "ok": all(check["ok"] for check in checks), "checks": checks}


def _provider_section(providers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    enabled = [name for name, provider in providers.items() if bool(provider.get("enabled", True))]
    checks = [
        {"name": "providers_configured", "ok": bool(providers), "detail": f"{len(providers)} known providers"},
        {"name": "providers_enabled", "ok": bool(enabled), "detail": f"{len(enabled)} enabled providers"},
    ]
    return {"name": "providers", "ok": all(check["ok"] for check in checks), "checks": checks}


def _integration_section(defaults: dict[str, Any], models: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checks = []
    role_defaults = {
        "chat": "chat_model",
        "autocomplete": "autocomplete_model",
        "embedding": "embedding_model",
    }
    for tool in ["continue", "aider"]:
        missing = []
        for role in required_roles(tool):
            role_name = role["name"]
            default_role = role_defaults.get(role_name, "chat_model")
            alias = defaults.get(default_role)
            if not alias or str(alias) not in models:
                missing.append(role_name)
        checks.append(
            {
                "name": f"integration:{tool}",
                "ok": not missing,
                "detail": "ready" if not missing else "missing roles: " + ", ".join(missing),
            }
        )
    return {"name": "integrations", "ok": all(check["ok"] for check in checks), "checks": checks}


def _mcp_section() -> dict[str, Any]:
    manifest = mcp_manifest()
    tools = manifest.get("tools", []) if isinstance(manifest, dict) else []
    checks = [
        {
            "name": "mcp_manifest",
            "ok": bool(tools),
            "detail": f"{len(tools) if isinstance(tools, list) else 0} tools advertised",
        }
    ]
    return {"name": "mcp", "ok": all(check["ok"] for check in checks), "checks": checks}


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
