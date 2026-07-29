"""Render one reviewable model decision into runtime and client handoffs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agents import AgentManager
from .benchmark_evidence import validate_measurement_record
from .integrations import IntegrationManager
from .models import Profile
from .role_routing import compare_role_models
from .runtime_catalog import RuntimeCatalog
from .secrets import contains_secret

_MAX_HANDOFF_BYTES = 1_048_576


SCHEMA_PATH = "schemas/aiplane-model-handoff-v1.schema.json"


def _checksum(value: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    )


def calibration_status(workspace: Path, model_name: str, runtime: str) -> dict[str, Any]:
    """Summarize controlled local/imported evidence without generalizing it."""
    root = workspace / ".aiplane" / "benchmarks"
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in sorted(root.glob("*.json")) if root.is_dir() else []:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("record_type") != "benchmark_measurements":
                continue
            record = validate_measurement_record(raw, source=str(path))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(f"{path.name}: {exc}")
            continue
        if record["model_name"] == model_name and str(record["runtime"].get("name") or runtime) == runtime:
            records.append(record)
    controlled = [row for row in records if row["calibration"]["status"] == "controlled"]
    summaries = [row["summary"] for row in controlled]
    sample_count = sum(int(summary.get("sample_count") or 0) for summary in summaries)
    return {
        "status": "controlled_comparable" if controlled else "unavailable",
        "record_count": len(controlled),
        "sample_count": sample_count,
        "runtime_match": bool(controlled),
        "context_match": "recorded_in_evidence" if controlled else "unresolved",
        "provenance": [row["provenance"].get("source") for row in controlled],
        "uncertainty": [summary.get("uncertainty") for summary in summaries],
        "warnings": warnings,
        "note": (
            "Only controlled local/imported records are summarized; missing evidence does not imply poor quality."
            if not controlled
            else "Controlled records are specific to their recorded runtime, environment, context, and decoding basis."
        ),
    }


class ModelHandoffManager:
    def __init__(self, profile: Profile):
        self.profile = profile

    def plan(
        self,
        *,
        role: str,
        model: str,
        runtime: str,
        context_tokens: int | None = None,
        integrations: list[str] | None = None,
        framework: str | None = None,
    ) -> dict[str, Any]:
        route = compare_role_models(
            self.profile, role, candidates=[model], runtime=runtime, context_tokens=context_tokens
        )
        selected = route.get("recommended")
        if not isinstance(selected, dict):
            alternatives = route.get("alternatives")
            if not isinstance(alternatives, list) or not alternatives or not isinstance(alternatives[0], dict):
                raise ValueError("selected model could not be evaluated for the requested role/runtime")
            selected = alternatives[0]
        runtime_plan = RuntimeCatalog(self.profile).capacity_plan(runtime, model, context_tokens=context_tokens)
        evidence = calibration_status(self.profile.workspace, model, runtime)
        integration_plans = {
            tool: IntegrationManager(self.profile).plan(tool, model_name=model, runtime=runtime)
            for tool in sorted(set(integrations or []))
        }
        agent = None
        if framework:
            manifest = AgentManager(self.profile).manifest(
                "model-handoff", framework=framework, model=model, runtime=runtime
            )
            agent = {"framework": framework, "manifest": manifest, "guardrails": manifest["guardrails"]}
        payload = {
            "$schema": SCHEMA_PATH,
            "schema_version": "1.0",
            "record_type": "model_handoff",
            "render_only": True,
            "profile": self.profile.name,
            "selection": selected,
            "role": role,
            "runtime": runtime,
            "context_tokens": context_tokens,
            "routing": route,
            "calibration_evidence": evidence,
            "runtime_capacity_plan": runtime_plan,
            "integration_plans": integration_plans,
            "agent": agent,
            "execution_boundary": {
                "starts_runtime": False,
                "runs_agents": False,
                "writes_configuration": False,
                "contacts_providers": False,
            },
            "notes": [
                "This is a reviewable composition of existing decision services; it does not apply the plans.",
                "Calibration evidence is advisory and environment-specific, not a universal quality score.",
            ],
        }
        if contains_secret(json.dumps(payload, sort_keys=True)):
            raise ValueError("model handoff contains secret-like material")
        payload["sha256"] = _checksum(payload)
        return payload


def validate_handoff_file(profile: Profile, source: Path | str) -> dict[str, Any]:
    path = Path(source)
    if not path.is_absolute():
        path = profile.workspace / path
    path = path.resolve()
    workspace = profile.workspace.resolve()
    if workspace not in path.parents or not path.is_file():
        raise PermissionError("model handoff path must be an existing regular file inside the workspace")
    if path.stat().st_size > _MAX_HANDOFF_BYTES:
        raise ValueError(f"model handoff exceeds the {_MAX_HANDOFF_BYTES}-byte review limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("model handoff must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("model handoff root must be a JSON object")
    errors: list[str] = []
    expected = {"$schema": SCHEMA_PATH, "schema_version": "1.0", "record_type": "model_handoff", "render_only": True}
    for key, value in expected.items():
        if payload.get(key) != value:
            errors.append(f"{key} must equal {value!r}")
    if payload.get("profile") != profile.name:
        errors.append("profile must match the selected profile")
    supplied = payload.get("sha256")
    without_checksum = dict(payload)
    without_checksum.pop("sha256", None)
    if supplied != _checksum(without_checksum):
        errors.append("sha256 does not match the handoff payload")
    if contains_secret(json.dumps(payload, sort_keys=True)):
        errors.append("model handoff contains secret-like material")
    return {
        "record_type": "model_handoff_validation",
        "path": str(path.relative_to(workspace)),
        "valid": not errors,
        "errors": errors,
        "mutates": False,
    }
