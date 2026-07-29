"""Portable, in-process budget guards for exported agent configurations.

This module deliberately does not launch, proxy, or supervise agents.  A
framework imports the generated adapter and calls its hooks around work it owns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

from .persistence import atomic_write_text


SCHEMA_PATH = "schemas/aiplane-agent-guardrails-v1.schema.json"
SCHEMA_VERSION = "1.0"
RECEIPT_SCHEMA_PATH = "schemas/aiplane-agent-guardrails-receipt-v1.schema.json"
_RATE_KEYS = {"input_usd_per_million_tokens", "output_usd_per_million_tokens"}

_LIMIT_KEYS = {
    "max_wall_seconds",
    "max_model_calls",
    "max_tool_calls",
    "max_retries",
    "max_input_tokens",
    "max_output_tokens",
    "max_total_tokens",
    "max_cost_usd",
}


class BudgetExceeded(RuntimeError):
    """Raised by an adapter hook before a configured budget is exceeded."""


def normalize_limits(limits: dict[str, object] | None) -> dict[str, int | float]:
    """Keep supported numeric guardrail limits and reject unsafe values."""
    normalized: dict[str, int | float] = {}
    for key, value in (limits or {}).items():
        if key not in _LIMIT_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"guardrail {key} must be a non-negative number")
        normalized[key] = float(value) if key == "max_cost_usd" else int(value)
    return normalized


def normalize_rate_card(rate_card: dict[str, object] | None) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in (rate_card or {}).items():
        if key not in _RATE_KEYS:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"rate card {key} must be a non-negative number")
        normalized[key] = float(value)
    return normalized


def render_guardrails(
    *,
    name: str,
    profile: str,
    framework: str,
    limits: dict[str, object] | None,
    rate_card: dict[str, object] | None = None,
    environment_sha256: str | None = None,
) -> dict[str, Any]:
    """Render a secret-free portable guardrails contract for one local run."""
    normalized = normalize_limits(limits)
    rates = normalize_rate_card(rate_card)
    enabled = bool(normalized)
    return {
        "$schema": SCHEMA_PATH,
        "schema_version": SCHEMA_VERSION,
        "record_type": "agent_guardrails",
        "render_only": True,
        "name": name,
        "profile": profile,
        "framework": framework,
        "scope": {"kind": "local_run", "durable_ledger": False},
        "limits": normalized,
        "cost": {
            "currency": "USD",
            "immediate_sources": ["provider_reported", "framework_reported", "pinned_rate_card"],
            "reconciliation": "optional_delayed_next_call_gate",
            "rate_card": rates,
        },
        "events": ["model_call", "model_response", "tool_call", "tool_result", "retry"],
        "adapter": {
            "language": "python",
            "environment_variable": "AIPLANE_GUARDRAILS_PATH",
            "hooks": [
                "before_model_call",
                "record_model_response",
                "before_tool_call",
                "record_tool_result",
                "record_retry",
            ],
            "enforcement": "in_process_callback",
        },
        "environment_sha256": environment_sha256,
        "execution_boundary": {
            "runs_agents": False,
            "proxies_model_requests": False,
            "reads_credentials": False,
            "contacts_billing_apis": False,
        },
        "notes": [
            "The target framework must call the adapter hooks for limits to be enforced.",
            "Provider billing reconciliation is delayed and can only block a subsequent call.",
        ],
        "enforcement_status": "adapter_required" if enabled else "no_limits_requested",
    }


def validate_guardrails(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["guardrails must be a JSON object"]
    errors: list[str] = []
    expected = {
        "$schema": SCHEMA_PATH,
        "schema_version": SCHEMA_VERSION,
        "record_type": "agent_guardrails",
        "render_only": True,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} must equal {value!r}")
    for key in ("name", "profile", "framework"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a non-empty string")
    try:
        normalize_limits(payload.get("limits") if isinstance(payload.get("limits"), dict) else None)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        normalize_rate_card(
            (payload.get("cost") or {}).get("rate_card") if isinstance(payload.get("cost"), dict) else None
        )
    except ValueError as exc:
        errors.append(str(exc))
    if not isinstance(payload.get("limits"), dict):
        errors.append("limits must be an object")
    return errors


@dataclass
class GuardrailAdapter:
    """Small framework-owned callback adapter for a single local agent run."""

    contract: dict[str, Any]
    run_id: str = "default"
    receipt_path: Path | None = None
    started_at: float = field(default_factory=time.monotonic)
    counters: dict[str, float] = field(
        default_factory=lambda: {
            "model_calls": 0,
            "tool_calls": 0,
            "retries": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0,
        }
    )
    stop_reason: str | None = None

    @classmethod
    def from_path(
        cls, path: Path | str, *, run_id: str = "default", receipt_path: Path | str | None = None
    ) -> "GuardrailAdapter":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        errors = validate_guardrails(payload)
        if errors:
            raise ValueError("invalid Aiplane guardrails: " + "; ".join(errors))
        return cls(payload, run_id=run_id, receipt_path=Path(receipt_path) if receipt_path else None)

    @property
    def limits(self) -> dict[str, int | float]:
        return normalize_limits(self.contract.get("limits"))

    def _check(self, key: str, observed: float) -> None:
        limit = self.limits.get(key)
        if limit is not None and observed > limit:
            self.stop_reason = key
            self._persist()
            raise BudgetExceeded(f"Aiplane guardrail exceeded: {key} ({observed} > {limit})")

    def _check_wall(self) -> None:
        self._check("max_wall_seconds", time.monotonic() - self.started_at)

    def before_model_call(self, *, estimated_input_tokens: int = 0, estimated_cost_usd: float = 0) -> None:
        if self.stop_reason:
            raise BudgetExceeded(f"Aiplane guardrail exceeded: {self.stop_reason}; refusing another model call")
        self._check_wall()
        self._check("max_model_calls", self.counters["model_calls"] + 1)
        self._check("max_input_tokens", self.counters["input_tokens"] + estimated_input_tokens)
        self._check("max_total_tokens", self.counters["total_tokens"] + estimated_input_tokens)
        self._check("max_cost_usd", self.counters["cost_usd"] + estimated_cost_usd)
        self.counters["model_calls"] += 1
        self._persist()

    def record_model_response(
        self, *, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float | None = None
    ) -> None:
        if cost_usd is None:
            rates = normalize_rate_card(
                self.contract.get("cost", {}).get("rate_card") if isinstance(self.contract.get("cost"), dict) else None
            )
            cost_usd = (
                input_tokens * rates.get("input_usd_per_million_tokens", 0)
                + output_tokens * rates.get("output_usd_per_million_tokens", 0)
            ) / 1_000_000
        for key, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens), ("cost_usd", cost_usd)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"{key} must be a non-negative number")
            self.counters[key] += value
        self.counters["total_tokens"] = self.counters["input_tokens"] + self.counters["output_tokens"]
        for limit, observed in (
            ("max_input_tokens", self.counters["input_tokens"]),
            ("max_output_tokens", self.counters["output_tokens"]),
            ("max_total_tokens", self.counters["total_tokens"]),
            ("max_cost_usd", self.counters["cost_usd"]),
        ):
            configured = self.limits.get(limit)
            if configured is not None and observed > configured:
                self.stop_reason = limit
                break
        self._persist()

    def before_tool_call(self) -> None:
        self._check_wall()
        self._check("max_tool_calls", self.counters["tool_calls"] + 1)
        self.counters["tool_calls"] += 1
        self._persist()

    def record_tool_result(self) -> None:
        self._check_wall()
        self._persist()

    def record_retry(self) -> None:
        self._check("max_retries", self.counters["retries"] + 1)
        self.counters["retries"] += 1
        self._persist()

    def receipt(self) -> dict[str, Any]:
        checksum = hashlib.sha256(
            json.dumps(self.contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "$schema": RECEIPT_SCHEMA_PATH,
            "schema_version": SCHEMA_VERSION,
            "record_type": "agent_guardrails_receipt",
            "run_id": self.run_id,
            "guardrails_sha256": "sha256:" + checksum,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "counters": self.counters,
            "cost_source": "framework_or_provider_reported_or_pinned_rate_card",
            "stop_reason": self.stop_reason,
            "enforcement_status": "stopped" if self.stop_reason else "active",
        }

    def _persist(self) -> None:
        if self.receipt_path:
            atomic_write_text(self.receipt_path, json.dumps(self.receipt(), indent=2, sort_keys=True))

    def report(self) -> dict[str, Any]:
        return self.receipt()


def validate_receipt(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["guardrails receipt must be a JSON object"]
    expected = {
        "$schema": RECEIPT_SCHEMA_PATH,
        "schema_version": SCHEMA_VERSION,
        "record_type": "agent_guardrails_receipt",
    }
    errors = [f"{key} must equal {value!r}" for key, value in expected.items() if payload.get(key) != value]
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"].strip():
        errors.append("run_id must be a non-empty string")
    guardrails_sha256 = payload.get("guardrails_sha256")
    if not isinstance(guardrails_sha256, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", guardrails_sha256):
        errors.append("guardrails_sha256 must be a string matching sha256:<64 hex chars>")
    recorded_at = payload.get("recorded_at")
    if not isinstance(recorded_at, str) or not recorded_at.strip():
        errors.append("recorded_at must be a non-empty string")
    enforcement_status = payload.get("enforcement_status")
    if enforcement_status not in ("active", "stopped"):
        errors.append("enforcement_status must be one of 'active', 'stopped'")
    if not isinstance(payload.get("counters"), dict):
        errors.append("counters must be an object")
    return errors
