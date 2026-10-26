from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .benchmark_evidence import validate_measurement_record
from .models import Profile
from .benchmark_identity import METRIC_DEFINITIONS, REQUIRED_CONTEXT, known
from .decoding import decoding_request

DIMENSIONS = {"runtime", "model", "machine", "quantization", "context"}


def compare_benchmarks(
    profile: Profile,
    *,
    by: str = "runtime",
    models: list[str] | None = None,
    runtimes: list[str] | None = None,
    suite: str | None = None,
    include_dry_run: bool = False,
) -> dict[str, Any]:
    if by not in DIMENSIONS:
        raise ValueError(f"benchmark comparison dimension must be one of: {', '.join(sorted(DIMENSIONS))}")
    model_filter = {str(value) for value in models or []}
    runtime_filter = {str(value) for value in runtimes or []}
    records, warnings = _load_records(profile.workspace)
    rows: list[dict[str, Any]] = []
    for path, payload in records:
        if payload.get("dry_run") and not include_dry_run:
            continue
        try:
            record = validate_measurement_record(payload, source=str(path))
        except ValueError as exc:
            warnings.append({"path": str(path), "reason": str(exc)})
            continue
        row = _row(path, record)
        if model_filter and row["model"] not in model_filter:
            continue
        if runtime_filter and row["runtime"] not in runtime_filter:
            continue
        if suite and row["suite"]["name"] != suite:
            continue
        rows.append(row)

    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        basis = _comparison_basis(row, by)
        row["varying_identity"] = _varying_identity(row, by)
        key = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
        group = groups.setdefault(
            key,
            {
                "id": key,
                "dimension": by,
                "basis": basis,
                "comparable": bool(row["suite"].get("comparability")),
                "calibrated": row["calibration"].get("status") == "controlled",
                "rows": [],
            },
        )
        group["rows"].append(row)

    result_groups = []
    for group in groups.values():
        group["rows"].sort(key=lambda row: (str(row.get(by) or ""), row["created_at"], row["path"]))
        identity_blockers = sorted({reason for row in group["rows"] for reason in row["identity_blockers"]})
        group["comparison_ready"] = (
            not identity_blockers
            and group["comparable"]
            and group["calibrated"]
            and len({json.dumps(row["varying_identity"], sort_keys=True) for row in group["rows"]}) >= 2
        )
        group["comparison_blockers"] = [
            blocker
            for blocker, applies in (
                ("suite has no explicit comparability contract", not group["comparable"]),
                ("records do not declare controlled calibration", not group["calibrated"]),
                (
                    f"fewer than two distinct {by} values",
                    len({json.dumps(row["varying_identity"], sort_keys=True) for row in group["rows"]}) < 2,
                ),
            )
            if applies
        ]
        group["comparison_blockers"].extend(identity_blockers)
        group["leaders"] = _leaders(group["rows"]) if group["comparison_ready"] else {}
        result_groups.append(group)
    result_groups.sort(key=lambda group: group["id"])
    return {
        "contract_version": "1.0",
        "record_type": "benchmark_comparison",
        "profile": profile.name,
        "dimension": by,
        "filters": {
            "models": sorted(model_filter),
            "runtimes": sorted(runtime_filter),
            "suite": suite,
            "include_dry_run": include_dry_run,
        },
        "records_scanned": len(records),
        "records_matched": len(rows),
        "groups": result_groups,
        "warnings": warnings,
        "notes": [
            "Leaders require matching displayed basis, an explicit suite comparability contract, and controlled calibration metadata.",
            "Quality, throughput, latency, placement, and policy remain separate; no universal score is calculated.",
            "TTFT leaders use only samples carrying explicit native telemetry provenance.",
            "Throughput average is a display mean of available server/client rates, not aggregate task throughput; source combinations are grouped separately.",
        ],
    }


def _load_records(workspace: Path) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, str]]]:
    root = workspace / ".aiplane" / "benchmarks"
    records: list[tuple[Path, dict[str, Any]]] = []
    warnings: list[dict[str, str]] = []
    if not root.exists():
        return records, warnings
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append({"path": str(path), "reason": type(exc).__name__})
            continue
        if not isinstance(payload, dict) or payload.get("record_type") != "benchmark_measurements":
            continue
        records.append((path, payload))
    return records, warnings


def _row(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    runtime = record.get("runtime") if isinstance(record.get("runtime"), dict) else {}
    settings = runtime.get("settings") if isinstance(runtime.get("settings"), dict) else {}
    names = runtime.get("names") if isinstance(runtime.get("names"), list) else []
    runtime_name = str(runtime.get("name") or (names[0] if len(names) == 1 else ",".join(str(v) for v in names)))
    environment = record.get("environment") if isinstance(record.get("environment"), dict) else {}
    hardware = environment.get("hardware") if isinstance(environment.get("hardware"), dict) else {}
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    runs = record.get("runs") if isinstance(record.get("runs"), list) else []
    exact_ttft = [
        float(run["ttft_ms"])
        for run in runs
        if run.get("ttft_ms") is not None and isinstance(run.get("telemetry_source"), str) and run["telemetry_source"]
    ]
    telemetry_sources = sorted(
        {
            str(run["telemetry_source"])
            for run in runs
            if isinstance(run.get("telemetry_source"), str) and run["telemetry_source"]
        }
    )
    blockers = _identity_blockers(record)
    return {
        "identity_blockers": blockers,
        "runtime_identity": runtime,
        "comparison_context": record.get("comparison_context", {}),
        "metric_definitions": record.get("metric_definitions", {}),
        "path": str(path),
        "created_at": str(record.get("created_at") or ""),
        "model": str(record.get("model_name") or ""),
        "provider_model": record.get("model"),
        "runtime": runtime_name or None,
        "machine": environment.get("fingerprint") or hardware.get("name"),
        "quantization": settings.get("quantization"),
        "context": settings.get("context_tokens") or settings.get("context"),
        "suite": record["suite"],
        "decoding": record.get("decoding", {}),
        "runtime_settings": settings,
        "summary": summary,
        "executed_tasks": sorted({run["task"] for run in runs}),
        "telemetry": {
            "sources": telemetry_sources,
            "ttft_exact_samples": len(exact_ttft),
            "average_exact_ttft_ms": round(sum(exact_ttft) / len(exact_ttft), 4) if exact_ttft else None,
        },
        "calibration": record.get("calibration", {"status": "uncontrolled"}),
        "environment": {
            "fingerprint": environment.get("fingerprint"),
            "hardware": hardware,
            "software": environment.get("software", {}),
        },
        "provenance": record.get("provenance", {}),
        "throughput_average_sources": sorted({tuple(run["throughput_average_sources"]) for run in runs}),
    }


def _identity_blockers(record: dict[str, Any]) -> list[str]:
    blockers = []
    context = record.get("comparison_context", {})
    for section, fields in REQUIRED_CONTEXT.items():
        part = context.get(section, {})
        for field in fields:
            if not isinstance(part, dict) or not known(part.get(field)):
                blockers.append(f"unknown comparison_context.{section}.{field}")
    for label, value in (
        ("suite.content_sha256", record["suite"].get("content_sha256")),
        ("runtime.version", record.get("runtime", {}).get("version")),
        ("runtime.settings", record.get("runtime", {}).get("settings")),
        ("runtime.settings.quantization", record.get("runtime", {}).get("settings", {}).get("quantization")),
        ("runtime.settings.context_tokens", record.get("runtime", {}).get("settings", {}).get("context_tokens")),
        ("environment.fingerprint", record.get("environment", {}).get("fingerprint")),
        ("environment.hardware", record.get("environment", {}).get("hardware")),
        ("environment.software", record.get("environment", {}).get("software")),
    ):
        if not known(value):
            blockers.append(f"unknown {label}")
    if record.get("dry_run"):
        blockers.append("preview is not measured evidence")
    for run in record["runs"]:
        if run.get("error"):
            blockers.append("run contains an execution error")
        evidence = run.get("decoding_evidence", {})
        protocol = evidence.get("protocol")
        try:
            expected, _ = decoding_request(str(protocol), record["decoding"])
            submitted = (
                protocol in {"ollama_api", "openai_compatible", "azure_openai", "anthropic_api"}
                and evidence.get("status") == "submitted"
                and evidence.get("requested") == record["decoding"]
                and evidence.get("unsupported") == []
                and evidence.get("submitted") == expected
            )
        except ValueError:
            submitted = False
        if not submitted:
            blockers.append("requested decoding has no matching submission evidence")
    metrics = record.get("metric_definitions", {})
    for field in (
        "quality_score",
        "performance_score",
        "elapsed_ms",
        "ttft_ms",
        "server_tokens_per_second",
        "client_tokens_per_second",
        "average_tokens_per_second",
    ):
        if any(run.get(field) is not None for run in record["runs"]) and (
            not isinstance(metrics.get(field), dict)
            or any(not known(metrics[field].get(key)) for key in METRIC_DEFINITIONS[field])
        ):
            blockers.append(f"unknown metric_definitions.{field}")
    return sorted(set(blockers))


def _varying_identity(row: dict[str, Any], dimension: str) -> Any:
    if dimension == "runtime":
        return {"runtime": row["runtime_identity"], "build": row["comparison_context"].get("runtime")}
    if dimension == "model":
        return {"model": row["provider_model"], "artifact": row["comparison_context"].get("model")}
    if dimension == "machine":
        return {"fingerprint": row["machine"], "hardware": row["environment"]["hardware"]}
    return row[dimension]


def _comparison_basis(row: dict[str, Any], dimension: str) -> dict[str, Any]:
    # Remove only the declared variable; all other submitted controls remain visible.
    context = dict(row["comparison_context"])
    context.pop(dimension, None)
    runtime = dict(row["runtime_identity"])
    settings = dict(row["runtime_settings"])
    if dimension == "quantization":
        settings.pop("quantization", None)
    if dimension == "context":
        settings.pop("context_tokens", None)
        settings.pop("context", None)
    runtime["settings"] = settings
    if dimension == "runtime":
        runtime = {}
    environment = dict(row["environment"])
    if dimension == "machine":
        environment.pop("fingerprint", None)
        environment.pop("hardware", None)
    calibration = dict(row["calibration"])
    if dimension == "context":
        calibration.pop("context_tokens", None)
    return {
        "suite": row["suite"],
        "executed_tasks": row["executed_tasks"],
        "provider_model": None if dimension == "model" else row["provider_model"],
        "decoding": row["decoding"],
        "comparison_context": context,
        "runtime": runtime,
        "environment": environment,
        "metric_definitions": row["metric_definitions"],
        "throughput_average_sources": row["throughput_average_sources"],
        "calibration": calibration,
        "dimensions": {name: row.get(name) for name in DIMENSIONS if name != dimension},
    }


def _leaders(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def best(field: str, *, lower: bool = False) -> dict[str, Any] | None:
        candidates = [(row, row["summary"].get(field)) for row in rows if row["summary"].get(field) is not None]
        if not candidates:
            return None
        row, value = sorted(candidates, key=lambda item: float(item[1]), reverse=not lower)[0]
        return {"value": value, "model": row["model"], "runtime": row["runtime"], "machine": row["machine"]}

    exact = [row for row in rows if row["telemetry"]["average_exact_ttft_ms"] is not None]
    ttft = None
    if exact:
        row = min(exact, key=lambda item: float(item["telemetry"]["average_exact_ttft_ms"]))
        ttft = {
            "value": row["telemetry"]["average_exact_ttft_ms"],
            "model": row["model"],
            "runtime": row["runtime"],
            "machine": row["machine"],
            "source": row["telemetry"]["sources"],
        }
    return {
        "quality_score": best("quality_score"),
        "performance_score": best("performance_score"),
        "server_tokens_per_second": best("average_server_tokens_per_second"),
        "client_tokens_per_second": best("average_client_tokens_per_second"),
        "average_tokens_per_second": best("average_tokens_per_second"),
        "elapsed_ms": best("average_elapsed_ms", lower=True),
        "ttft_ms": ttft,
    }
