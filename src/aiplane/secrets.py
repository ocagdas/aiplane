from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"-----BEGIN CERTIFICATE-----"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"
    ),
    re.compile(r"\b(?:sk|pk|ghp|github_pat|xoxb|xoxp)_[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


SENSITIVE_KEYS = {
    "api_key",
    "token",
    "secret",
    "password",
    "client_secret",
    "subscription_key",
    "bearer_token",
}


def credentials_path(
    path: Path | str | None = None, config_path: Path | str | None = None
) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get("AIPLANE_CREDENTIALS")
    if env_path:
        return Path(env_path).expanduser().resolve()
    from .config import load_local_config, local_config_path, project_root

    resolved_config_path = local_config_path(config_path)
    if resolved_config_path.exists():
        configured = load_local_config(resolved_config_path).get("credentials_path")
        if configured:
            return Path(str(configured)).expanduser().resolve()
    return project_root() / ".aiplane" / "credentials.yaml"


def contains_secret(value: Any) -> bool:
    text = _stringify(value)
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED_SECRET]"
                if str(key).lower() in SENSITIVE_KEYS and inner
                else redact(inner)
            )
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [redact(inner) for inner in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    redacted = redacted.replace("[REDACTED_SECRET]'", "[REDACTED_SECRET]")
    redacted = redacted.replace('[REDACTED_SECRET]"', "[REDACTED_SECRET]")
    return redacted


class CredentialStore:
    def __init__(self, path: Path | str | None = None):
        self.path = credentials_path(path)
        self.config = self._load()

    def list(self) -> dict[str, Any]:
        providers = (
            self.config.get("providers", {}) if isinstance(self.config, dict) else {}
        )
        rows = []
        for provider, provider_config in sorted(providers.items()):
            accounts = (
                provider_config.get("accounts", {})
                if isinstance(provider_config, dict)
                else {}
            )
            for account, value in sorted(accounts.items()):
                if not isinstance(value, dict):
                    continue
                rows.append(
                    {
                        "ref": f"{provider}.{account}",
                        "provider": provider,
                        "account": account,
                        "endpoint": value.get("endpoint"),
                        "api_key_env": value.get("api_key_env"),
                        "has_api_key": bool(value.get("api_key")),
                        "has_token": bool(
                            value.get("token") or value.get("bearer_token")
                        ),
                        "notes": value.get("notes"),
                    }
                )
        return {
            "name": "credentials",
            "credentials": rows,
        }

    def show(self, ref: str) -> dict[str, Any]:
        provider, account = parse_credential_ref(ref)
        value = self._account(provider, account)
        if value is None:
            raise ValueError(f"credential not found: {ref}")
        return {
            "name": "credential",
            "ref": f"{provider}.{account}",
            "path": str(self.path),
            "credential": redact(value),
        }

    def resolve(self, ref: str | None) -> dict[str, Any]:
        if not ref:
            return {}
        provider, account = parse_credential_ref(ref)
        value = self._account(provider, account)
        if value is None:
            raise ValueError(f"credential not found: {ref}")
        result = dict(value)
        result.setdefault("provider", provider)
        result.setdefault("account", account)
        result.setdefault("ref", f"{provider}.{account}")
        return result

    def api_key_env(self, ref: str | None) -> str | None:
        value = self.resolve(ref)
        env_name = value.get("api_key_env") or value.get("token_env")
        return str(env_name) if env_name else None

    def api_key(self, ref: str | None) -> str | None:
        value = self.resolve(ref)
        env_name = value.get("api_key_env") or value.get("token_env")
        if env_name and os.environ.get(str(env_name)):
            return os.environ[str(env_name)]
        key = value.get("api_key") or value.get("token") or value.get("bearer_token")
        return str(key) if key else None

    def endpoint(self, ref: str | None) -> str | None:
        value = self.resolve(ref)
        endpoint = value.get("endpoint")
        return str(endpoint) if endpoint else None

    def _account(self, provider: str, account: str) -> dict[str, Any] | None:
        providers = (
            self.config.get("providers", {}) if isinstance(self.config, dict) else {}
        )
        provider_config = (
            providers.get(provider, {}) if isinstance(providers, dict) else {}
        )
        accounts = (
            provider_config.get("accounts", {})
            if isinstance(provider_config, dict)
            else {}
        )
        value = accounts.get(account) if isinstance(accounts, dict) else None
        return value if isinstance(value, dict) else None

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        from .config import parse_yaml

        return parse_yaml(self.path.read_text(encoding="utf-8"))


def parse_credential_ref(ref: str) -> tuple[str, str]:
    if not ref:
        raise ValueError("credential ref is required")
    if "/" in ref:
        provider, account = ref.split("/", 1)
    elif "." in ref:
        provider, account = ref.split(".", 1)
    else:
        raise ValueError("credential ref must be provider.account or provider/account")
    if not provider or not account:
        raise ValueError("credential ref must be provider.account or provider/account")
    return provider, account


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_stringify(inner)}" for key, inner in value.items())
    if isinstance(value, list):
        return "\n".join(_stringify(inner) for inner in value)
    return str(value)
