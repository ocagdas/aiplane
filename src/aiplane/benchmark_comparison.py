from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .benchmark_evidence import validate_measurement_record
from .models import Profile

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
        key = hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]
        group = groups.setdefault(
            key,
            {
                "id": key,
                "dimension": by,
                "basis": basis,
                "comparable": bool(row["suite"].get("comparability")),
                "rows": [],
            },
        )
        group["rows"].append(row)

    result_groups = []
    for group in groups.values():
        group["rows"].sort(key=lambda row: (str(row.get(by) or ""), row["created_at"], row["path"]))
        group["comparison_ready"] = group["comparable"] and len({str(row.get(by)) for row in group["rows"]}) >= 2
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
            "Rows are comparable only when the suite declares comparability and the displayed basis matches.",
            "Quality, throughput, latency, placement, and policy remain separate; no universal score is calculated.",
            "TTFT leaders use only samples carrying explicit native telemetry provenance.",
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
    return {
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
        "telemetry": {
            "sources": telemetry_sources,
            "ttft_exact_samples": len(exact_ttft),
            "average_exact_ttft_ms": round(sum(exact_ttft) / len(exact_ttft), 4) if exact_ttft else None,
        },
        "environment": {
            "fingerprint": environment.get("fingerprint"),
            "hardware": hardware,
            "software": environment.get("software", {}),
        },
        "provenance": record.get("provenance", {}),
    }


def _comparison_basis(row: dict[str, Any], dimension: str) -> dict[str, Any]:
    dimensions = {
        name: row.get(name) for name in ("runtime", "model", "machine", "quantization", "context") if name != dimension
    }
    return {
        "suite": {
            "name": row["suite"].get("name"),
            "version": row["suite"].get("version"),
            "kind": row["suite"].get("kind"),
            "comparability": row["suite"].get("comparability"),
        },
        "decoding": row.get("decoding", {}),
        "dimensions": dimensions,
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
        "tokens_per_second": best("average_tokens_per_second"),
        "elapsed_ms": best("average_elapsed_ms", lower=True),
        "ttft_ms": ttft,
    }
