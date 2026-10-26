"""Validate requested generation controls and describe their wire representation.

Submission proves what this client sent, never what a remote model actually used.
"""

from __future__ import annotations

import math
from typing import Any


def validate_decoding(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("benchmark decoding must be a mapping")
    unknown = set(raw) - {"temperature", "top_p", "seed", "max_output_tokens"}
    if unknown:
        raise ValueError(f"unsupported decoding fields: {', '.join(sorted(map(str, unknown)))}")
    result = dict(raw)
    for key, limit in (("temperature", 2), ("top_p", 1)):
        if key in result:
            value = result[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= limit
                or not math.isfinite(value)
            ):
                raise ValueError(f"benchmark decoding {key} must be between 0 and {limit}")
    for key in ("seed", "max_output_tokens"):
        if key in result:
            value = result[key]
            if isinstance(value, bool) or not isinstance(value, int) or (key == "max_output_tokens" and value < 1):
                raise ValueError(
                    f"benchmark decoding {key} must be {'a positive integer' if key == 'max_output_tokens' else 'an integer'}"
                )
    return result


class UnsupportedDecoding(ValueError):
    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        super().__init__(
            f"{evidence['protocol']} does not support requested decoding: {', '.join(evidence['unsupported'])}"
        )


class DecodingRejected(RuntimeError):
    def __init__(self, evidence: dict[str, Any], status: int):
        self.evidence = {**evidence, "status": "rejected", "http_status": status}
        super().__init__(
            f"{evidence['protocol']} rejected the request (HTTP {status}); settings were not removed or retried"
        )


def decoding_request(protocol: str, raw: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    requested = validate_decoding({} if raw is None else raw)
    unsupported = [
        key
        for key in requested
        if protocol == "anthropic_api" and (key == "seed" or (key == "temperature" and requested[key] > 1))
    ]
    evidence = {
        "protocol": protocol,
        "requested": requested,
        "submitted": {},
        "unsupported": unsupported,
        "status": "unsupported" if unsupported else "planned",
        "provider_confirmed": None,
    }
    if unsupported:
        raise UnsupportedDecoding(evidence)
    mapping = {"max_output_tokens": "num_predict" if protocol == "ollama_api" else "max_tokens"}
    settings = {mapping.get(key, key): value for key, value in requested.items()}
    if protocol == "anthropic_api":
        settings.setdefault("max_tokens", 1024)
    wire = {"options": settings} if protocol == "ollama_api" and settings else settings
    evidence["submitted"] = wire
    evidence["status"] = "submitted"
    return wire, evidence
