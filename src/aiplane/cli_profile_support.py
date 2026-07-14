from __future__ import annotations

from .model_catalog import ModelCatalog


def _profile_summary(profile, default_name: str | None = None) -> dict[str, object]:
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "workspace": str(profile.workspace),
        "selected": _profile_selected(profile, default_name),
        "environment": profile.environment,
        "hardware": profile.hardware,
        "models": profile.models,
        "targets": profile.targets,
        "repository": profile.repository,
        "tools": profile.tools,
        "approvals": profile.approvals,
        "backends": profile.backends,
    }


def _profile_selected(profile, default_name: str | None = None) -> dict[str, object]:
    providers = ModelCatalog(profile).providers()
    models = profile.models.get("models", {}) if isinstance(profile.models, dict) else {}
    targets = profile.targets.get("targets", {}) if isinstance(profile.targets, dict) else {}
    hardware_selected = profile.hardware.get("selected", {}) if isinstance(profile.hardware, dict) else {}
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "environment": {
            "active": profile.environment.get("active"),
            "config": _dict_value(profile.environment.get("modes", {})).get(str(profile.environment.get("active")), {}),
        },
        "hardware": {
            "origin": hardware_selected.get("origin"),
            "custom": hardware_selected.get("custom"),
            "values": hardware_selected.get("values", {}),
        },
        "providers": [
            {"name": name, **provider}
            for name, provider in _dict_value(providers).items()
            if bool(provider.get("enabled", True))
        ],
        "model_defaults": (profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}),
        "models": [
            {"name": name, **model} for name, model in _dict_value(models).items() if bool(model.get("enabled", True))
        ],
        "targets": {
            "default": (profile.targets.get("default") if isinstance(profile.targets, dict) else None),
            "config": (
                _dict_value(targets).get(str(profile.targets.get("default")), {})
                if isinstance(profile.targets, dict)
                else {}
            ),
        },
        "repository": profile.repository,
    }


def _validate_profile(profile) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    for filename in [
        "hardware.yaml",
        "backends.yaml",
        "repository.yaml",
        "tools.yaml",
        "approvals.yaml",
        "environment.yaml",
        "models.yaml",
        "targets.yaml",
        "orchestrators.yaml",
    ]:
        path = profile.root / filename
        checks.append({"name": f"file:{filename}", "ok": path.exists(), "detail": str(path)})

    active_env = profile.environment.get("active") if isinstance(profile.environment, dict) else None
    modes = _dict_value(profile.environment.get("modes", {})) if isinstance(profile.environment, dict) else {}
    checks.append(
        {
            "name": "environment:active_mode",
            "ok": bool(active_env in modes),
            "detail": active_env,
        }
    )

    providers = ModelCatalog(profile).providers()
    models = _dict_value(profile.models.get("models", {})) if isinstance(profile.models, dict) else {}
    defaults = _dict_value(profile.models.get("defaults", {})) if isinstance(profile.models, dict) else {}
    for role, name in defaults.items():
        model = models.get(str(name))
        checks.append(
            {
                "name": f"model_default:{role}",
                "ok": isinstance(model, dict),
                "detail": name,
            }
        )
        if isinstance(model, dict) and not bool(model.get("enabled", True)):
            checks.append(
                {
                    "name": f"model_default_enabled:{role}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is configured but disabled",
                }
            )
    for name, model in models.items():
        provider = str(model.get("provider", "")) if isinstance(model, dict) else ""
        checks.append(
            {
                "name": f"model_provider:{name}",
                "ok": provider in providers,
                "detail": provider,
            }
        )
        if (
            provider in providers
            and bool(model.get("enabled", True))
            and not bool(providers[provider].get("enabled", True))
        ):
            checks.append(
                {
                    "name": f"provider_enabled:{provider}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is catalogued, but runtime endpoint {provider} is disabled",
                }
            )

    targets = _dict_value(profile.targets.get("targets", {})) if isinstance(profile.targets, dict) else {}
    default_target = profile.targets.get("default") if isinstance(profile.targets, dict) else None
    checks.append(
        {
            "name": "target:default",
            "ok": bool(default_target in targets),
            "detail": default_target,
        }
    )

    return {
        "name": profile.name,
        "ok": all(bool(check["ok"]) for check in checks if not check.get("warning")),
        "checks": checks,
    }


_AZ_SENSITIVE_FLAGS = {
    "--subscription",
    "--tenant",
    "--tenant-id",
    "--account-name",
    "--username",
    "--password",
    "--token",
    "--access-token",
    "--api-key",
    "--client-id",
    "--client-secret",
    "--sas-token",
    "--connection-string",
}

_AZ_SENSITIVE_JSON_KEYS = {
    "id",
    "tenantid",
    "subscriptionid",
    "userid",
    "username",
    "principalid",
    "clientid",
    "objectid",
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "secret",
    "connectionstring",
}


def _dict_value(value: object) -> dict:
    return value if isinstance(value, dict) else {}
