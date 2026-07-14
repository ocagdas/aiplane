from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_SSH_USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}")
_ALLOWED_ENDPOINT_SCHEMES = {"http", "https"}


def validate_ssh_host(value: object, field: str = "ssh.host", *, default: str | None = None) -> str:
    candidate = str(value or "").strip() or str(default or "").strip()
    if not candidate:
        raise ValueError(f"target is missing required field {field}")
    if candidate.startswith("-"):
        raise ValueError(f"target field {field} must not start with -")
    if any(character.isspace() or ord(character) < 32 for character in candidate):
        raise ValueError(f"target field {field} contains whitespace or control characters")
    unbracketed = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    if candidate.startswith("[") != candidate.endswith("]"):
        raise ValueError(f"target field {field} has invalid IP brackets")
    try:
        address = ipaddress.ip_address(unbracketed)
    except ValueError:
        labels = unbracketed.rstrip(".").split(".")
        if len(unbracketed) > 253 or not labels or not all(_HOST_LABEL.fullmatch(label) for label in labels):
            raise ValueError(f"target field {field} must be a valid hostname or IP address") from None
        return unbracketed.rstrip(".")
    return address.compressed


def validate_ssh_user(value: object, field: str = "ssh.user", *, required: bool = False) -> str:
    candidate = str(value or "").strip()
    if not candidate and not required:
        return ""
    if not candidate:
        raise ValueError(f"target is missing required field {field}")
    if not _SSH_USER.fullmatch(candidate):
        raise ValueError(f"target field {field} must be a valid SSH username and must not start with -")
    return candidate


def validate_port(value: object, field: str, *, default: int = 22) -> int:
    raw = value if value is not None else default
    if isinstance(raw, bool):
        raise ValueError(f"target field {field} must be an integer in the range 1-65535")
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"target field {field} must be an integer in the range 1-65535") from None
    if str(raw).strip() != str(port) or not 1 <= port <= 65535:
        raise ValueError(f"target field {field} must be an integer in the range 1-65535")
    return port


def validate_http_endpoint(value: object, field: str = "endpoint") -> str:
    candidate = str(value or "").strip()
    if any(character.isspace() or ord(character) < 32 for character in candidate):
        raise ValueError(f"target field {field} contains whitespace or control characters")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"target field {field} is not a valid URL: {exc}") from None
    if parsed.scheme.lower() not in _ALLOWED_ENDPOINT_SCHEMES:
        raise ValueError(f"target field {field} must use http or https")
    if not parsed.netloc or parsed.hostname is None:
        raise ValueError(f"target field {field} must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"target field {field} must not embed credentials")
    validate_ssh_host(parsed.hostname, f"{field} hostname")
    if port is not None:
        validate_port(port, f"{field} port")
    if parsed.fragment:
        raise ValueError(f"target field {field} must not include a URL fragment")
    return candidate


def ssh_forward_host(host: str) -> str:
    return f"[{host}]" if ":" in host else host
