"""Offline ensemble configuration compiler. Never starts agents or contacts providers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
from urllib.parse import urlsplit

from .config import parse_yaml
from .harness_catalog import compatibility, harness_catalog, harness_record
from .model_catalog import ModelCatalog
from .models import Profile
from .network_validation import validate_http_endpoint
from .policy import PolicyEngine
from .secrets import contains_secret

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]*\Z")


def _mapping(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError(f"{label} must be a mapping with only documented fields")
    return value


def _id(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a simple identifier")
    return value


def _reference(value, label):
    if not isinstance(value, str) or not value or len(value) > 512 or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be a non-empty string without control characters")
    return value


def _relative_path(value, workspace, label):
    value = _reference(value, label)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"{label} must be a relative workspace path without traversal")
    if not (workspace / path).resolve().is_relative_to(workspace.resolve()):
        raise ValueError(f"{label} resolves outside the workspace")
    return value


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field in ensemble specification")
        result[key] = value
    return result


def _ensemble_yaml(text: str) -> dict[str, Any]:
    # Match the restricted parser's mapping scopes while rejecting silent overwrites.
    scopes: list[tuple[int, set[str]]] = [(-1, set())]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, value = raw.strip().split(":", 1)
        while len(scopes) > 1 and indent <= scopes[-1][0]:
            scopes.pop()
        keys = scopes[-1][1]
        if key.strip() in keys:
            raise ValueError("duplicate YAML field in ensemble specification")
        keys.add(key.strip())
        if not value.strip():
            scopes.append((indent, set()))
    return parse_yaml(text)


def load_ensemble(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("ensemble specification exceeds 1 MiB")
    text = path.read_text(encoding="utf-8")
    try:
        spec = json.loads(text, object_pairs_hook=_unique_json) if path.suffix == ".json" else _ensemble_yaml(text)
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError("invalid ensemble specification") from None
    if contains_secret(spec):
        raise ValueError("ensemble specification must contain references, never credential values")
    return spec


def ensemble_template():
    return {
        "schema_version": 1,
        "name": "hybrid-development",
        "artifact_directory": ".aiplane/ensemble-artifacts",
        "roles": {
            "planner": {
                "harness": "langgraph",
                "surface": "python",
                "model_alias": "cloud_planner",
                "auth": "provider_env",
                "depends_on": [],
            },
            "implementer": {
                "harness": "opencode",
                "surface": "cli",
                "model_alias": "local_coder",
                "auth": "none",
                "depends_on": ["planner"],
            },
            "reviewer": {
                "harness": "claude-code",
                "surface": "cli",
                "harness_model": "default",
                "auth": "harness_login",
                "depends_on": ["implementer"],
            },
        },
    }


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _policy(decisions):
    return {
        "allowed": all(d.allowed for d in decisions),
        "requires_approval": any(d.requires_approval for d in decisions),
        "reasons": [d.reason for d in decisions],
    }


def resolve_role(role_name: str, role: dict[str, Any], profile: Profile) -> dict[str, Any]:
    _id(role_name, "role name")
    role = _mapping(
        role,
        {"harness", "surface", "model_alias", "harness_model", "auth", "credential_env", "depends_on", "guidance"},
        "role",
    )
    harness = _id(role.get("harness"), "harness")
    record = harness_record(harness)
    surface = _id(role.get("surface"), "surface")
    auth = role.get("auth")
    if auth not in {"provider_env", "harness_login", "product_env", "none"}:
        raise ValueError("role auth must be provider_env, harness_login, product_env, or none")
    if ("model_alias" in role) == ("harness_model" in role):
        raise ValueError("each role requires exactly one of model_alias and harness_model")
    dependencies = role.get("depends_on", [])
    if not isinstance(dependencies, list) or len(set(map(str, dependencies))) != len(dependencies):
        raise ValueError("depends_on must be a list of unique role names")
    dependencies = [_id(name, "dependency") for name in dependencies]
    policy = PolicyEngine(profile)
    native = "harness_model" in role
    if native:
        model_id = _reference(role["harness_model"], "harness_model")
        provider, protocol, endpoint = record["native_provider"], "harness_native", None
        decisions = [policy.provider_decision(provider or harness), policy.cloud_decision()]
        credential_env = role.get("credential_env")
        if auth == "product_env" and harness == "cursor" and credential_env != "CURSOR_API_KEY":
            raise ValueError("Cursor product_env requires credential_env: CURSOR_API_KEY")
        binding = {
            "namespace": "harness_native",
            "model_id": model_id,
            "provider": provider,
            "protocol": protocol,
            "endpoint": endpoint,
        }
    else:
        alias = _id(role["model_alias"], "model_alias")
        models = profile.models.get("models", {}) or {}
        model = models.get(alias)
        if not isinstance(model, dict):
            raise ValueError("model_alias must be a reviewed profile-owned model; use models promote/add first")
        catalog = ModelCatalog(profile)
        provider = _id(model.get("provider"), "profile provider")
        provider_config = catalog.providers().get(provider, {})
        overrides = model.get("provider_config", {}) or {}
        if not isinstance(overrides, dict):
            raise ValueError("model provider_config must be a mapping")
        provider_config = {**provider_config, **overrides}
        if not provider_config.get("enabled", True):
            raise ValueError("ensemble model provider is disabled")
        protocol = model.get("protocol") or provider_config.get("protocol")
        endpoint = model.get("endpoint") or provider_config.get("endpoint")
        model_id = _reference(model.get("model"), "profile model ID")
        # Codex is a Responses client; a chat-compatible endpoint alone does not prove Responses support.
        if harness == "codex" and "responses" in (
            model.get("supported_apis") or provider_config.get("supported_apis") or []
        ):
            protocol = "responses"
        if protocol is not None:
            _id(protocol, "profile protocol")
        if endpoint:
            _reference(endpoint, "profile endpoint")
            endpoint = validate_http_endpoint(endpoint)
            if urlsplit(endpoint).query:
                raise ValueError("ensemble endpoints must not include query strings")
        credential_env = role.get("credential_env") or model.get("api_key_env") or provider_config.get("api_key_env")
        if auth == "none":
            hostname = urlsplit(endpoint or "").hostname
            if not model.get("local", False) or hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("auth none requires an explicitly local model on a loopback endpoint")
            credential_env = None
        decisions = [policy.model_decision(alias)]
        binding = {
            "namespace": "profile",
            "alias": alias,
            "model_id": model_id,
            "provider": provider,
            "protocol": protocol,
            "endpoint": endpoint,
        }
    if credential_env is not None and (not isinstance(credential_env, str) or not _ENV.fullmatch(credential_env)):
        raise ValueError("credential_env must be an uppercase environment variable name")
    if auth in {"provider_env", "product_env"} and not credential_env:
        raise ValueError("environment authentication requires a credential_env reference")
    if auth in {"none", "harness_login"} and role.get("credential_env"):
        raise ValueError("this authentication mode does not accept credential_env")
    if auth == "harness_login":
        credential_env = None
    binding["auth"] = {"mode": auth, "credential_env": credential_env}
    if contains_secret(binding):
        raise ValueError("resolved model binding contains credential-like data")
    result = {
        "name": role_name,
        "harness": harness,
        "surface": surface,
        "binding": binding,
        "depends_on": dependencies,
        "compatibility": compatibility(
            harness, surface, protocol=protocol, provider=provider, native=native, auth=auth
        ),
        "policy": _policy(decisions),
    }
    if not native and not endpoint:
        result["compatibility"] = {
            **result["compatibility"],
            "status": "unknown",
            "reason": "No HTTP endpoint resolved; a qualified adapter must supply transport.",
        }
    if "guidance" in role:
        result["guidance"] = _relative_path(role["guidance"], profile.workspace, "guidance")
    return result


def plan_ensemble(spec: dict[str, Any], profile: Profile) -> dict[str, Any]:
    if contains_secret(spec):
        raise ValueError("ensemble specification must contain references, never credential values")
    spec = _mapping(spec, {"schema_version", "name", "artifact_directory", "roles"}, "ensemble")
    if type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise ValueError("ensemble schema_version must be 1")
    name = _id(spec.get("name"), "ensemble name")
    roles = spec.get("roles")
    if not isinstance(roles, dict) or not roles or len(roles) > 64:
        raise ValueError("ensemble requires between 1 and 64 named roles")
    for role_name in roles:
        _id(role_name, "role name")
    resolved = {name: resolve_role(name, role, profile) for name, role in sorted(roles.items())}
    order, visiting, visited = [], set(), set()

    def visit(name):
        if name not in resolved:
            raise ValueError("depends_on references an unknown role")
        if name in visiting:
            raise ValueError("ensemble dependencies must form a DAG, without cycles")
        if name in visited:
            return
        visiting.add(name)
        for dependency in resolved[name]["depends_on"]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        order.append(name)

    for role_name in resolved:
        visit(role_name)
    blocked = any(
        r["compatibility"]["status"] == "unsupported" or not r["policy"]["allowed"] for r in resolved.values()
    )
    result = {
        "schema_version": 1,
        "kind": "aiplane-ensemble-handoff",
        "name": name,
        "profile": profile.name,
        "artifact_directory": _relative_path(
            spec.get("artifact_directory", ".aiplane/ensemble-artifacts"), profile.workspace, "artifact_directory"
        ),
        "roles": resolved,
        "dependency_order": order,
        "configuration_status": "blocked" if blocked else "review_required",
        "execution_ready": False,
        "qualification_required": [
            "runner adapter",
            "installed harness version",
            "account/model access",
            "tool calling",
            "sandbox and permissions",
            "artifact exchange and dependency enforcement",
        ],
        "provenance": {
            "spec_sha256": _digest(spec),
            "catalog_sha256": _digest(harness_catalog()),
            "binding_sha256": _digest(resolved),
        },
    }

    if contains_secret(result):
        raise ValueError("resolved ensemble contains credential-like data")
    return result


def doctor_ensemble(plan: dict[str, Any], profile: Profile) -> dict[str, Any]:
    observations = {}
    for name, role in plan["roles"].items():
        record = harness_record(role["harness"])
        executable = record["executable"]
        env = role["binding"]["auth"]["credential_env"]
        observations[name] = {
            "executable_present": bool(shutil.which(executable)) if executable and role["surface"] == "cli" else None,
            "credential_env_present": bool(os.environ.get(env)) if env else None,
            "guidance_present": (profile.workspace / role["guidance"]).is_file() if role.get("guidance") else None,
            "account_access": "not_checked",
            "endpoint_health": "not_checked",
            "tool_calling": "not_checked",
        }
    return {
        **plan,
        "observations": observations,
        "doctor_scope": "offline; no subprocesses, network, credentials readout, or execution",
    }
