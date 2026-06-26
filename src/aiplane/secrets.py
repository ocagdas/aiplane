from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"-----BEGIN CERTIFICATE-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{12,})"),
    re.compile(r"\b(?:sk|pk|ghp|github_pat|xoxb|xoxp)_[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def contains_secret(value: Any) -> bool:
    text = _stringify(value)
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [redact(inner) for inner in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    redacted = redacted.replace("[REDACTED_SECRET]'", "[REDACTED_SECRET]")
    redacted = redacted.replace("[REDACTED_SECRET]\"", "[REDACTED_SECRET]")
    return redacted


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"{key}: {_stringify(inner)}" for key, inner in value.items())
    if isinstance(value, list):
        return "\n".join(_stringify(inner) for inner in value)
    return str(value)
