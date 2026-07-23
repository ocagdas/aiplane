"""Portable benchmark suites and user-supplied measurement evidence."""

from __future__ import annotations

import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import parse_yaml
from .persistence import atomic_write_text
from .secrets import contains_secret

CONTRACT_VERSION = "1.0"
SUITE_KINDS = {"smoke", "quality", "performance", "mixed"}
EVALUATOR_TYPES = {"expected_terms", "exact_match", "regex", "json", "command"}
METRICS = {
    "quality_score",
    "performance_score",
    "elapsed_ms",
    "ttft_ms",
    "prompt_tokens",
    "output_tokens",
    "tokens_per_second",
}


def load_suite(path: Path) -> dict[str, Any]:
    payload = _read_mapping(path)
    return validate_suite(payload, source=str(path))


def validate_suite(payload: dict[str, Any], *, source: str = "inline") -> dict[str, Any]:
    if payload.get("schema_version") != CONTRACT_VERSION:
        raise ValueError(f"benchmark suite schema_version must be {CONTRACT_VERSION}")
    name = _required_text(payload, "name", "benchmark suite")
    version = _required_text(payload, "version", "benchmark suite")
    kind = str(payload.get("kind") or "")
    if kind not in SUITE_KINDS:
        raise ValueError(f"benchmark suite kind must be one of: {', '.join(sorted(SUITE_KINDS))}")
    repeats = _bounded_int(payload.get("repeats", 1), "benchmark suite repeats", minimum=1, maximum=100)
    allow_commands = bool(payload.get("allow_command_evaluators", False))
    decoding = _validate_decoding(payload.get("decoding", {}))
    comparability = _validate_comparability(payload.get("comparability"))
    metrics = _string_list(payload.get("metrics", []), "benchmark suite metrics")
    unknown_metrics = sorted(set(metrics) - METRICS)
    if unknown_metrics:
        raise ValueError(f"unknown benchmark suite metrics: {', '.join(unknown_metrics)}")
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, dict) or not raw_tasks:
        raise ValueError("benchmark suite must contain a non-empty tasks mapping")
    tasks = {}
    for task_name, raw in sorted(raw_tasks.items(), key=lambda item: str(item[0])):
        task = str(task_name).strip()
        if not task or "/" in task or "\\" in task:
            raise ValueError("benchmark task names must be simple names")
        if not isinstance(raw, dict):
            raise ValueError(f"benchmark task {task!r} must be a mapping")
        prompt = _required_text(raw, "prompt", f"benchmark task {task!r}")
        evaluator = _validate_evaluator(raw, allow_commands, task)
        tasks[task] = {
            "prompt": prompt,
            "expected_terms": _string_list(raw.get("expected_terms", []), f"task {task!r} expected_terms"),
            "timeout_seconds": _bounded_int(
                raw.get("timeout_seconds", 60), f"task {task!r} timeout_seconds", minimum=1, maximum=3600
            ),
            "evaluator": evaluator,
            "metadata": _mapping(raw.get("metadata", {}), f"task {task!r} metadata"),
        }
    canonical = {
        "schema_version": CONTRACT_VERSION,
        "name": name,
        "version": version,
        "kind": kind,
        "repeats": repeats,
        "decoding": decoding,
        "metrics": metrics,
        "comparability": comparability,
        "allow_command_evaluators": allow_commands,
        "tasks": tasks,
        "source": source,
    }
    _reject_secret_material(canonical, "benchmark suite")
    return canonical


def validate_measurement_record(payload: dict[str, Any], *, source: str = "inline") -> dict[str, Any]:
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"benchmark measurement contract_version must be {CONTRACT_VERSION}")
    if payload.get("record_type") != "benchmark_measurements":
        raise ValueError("benchmark measurement record_type must be benchmark_measurements")
    model_name = _required_text(payload, "model_name", "benchmark measurement")
    suite = _mapping(payload.get("suite"), "benchmark measurement suite")
    suite_name = _required_text(suite, "name", "benchmark measurement suite")
    suite_version = _required_text(suite, "version", "benchmark measurement suite")
    kind = str(suite.get("kind") or "")
    if kind not in SUITE_KINDS:
        raise ValueError(f"benchmark measurement suite kind must be one of: {', '.join(sorted(SUITE_KINDS))}")
    comparability = _validate_comparability(suite.get("comparability"))
    raw_runs = payload.get("runs")
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("benchmark measurement runs must be a non-empty list")
    runs = [_validate_run(run, index) for index, run in enumerate(raw_runs)]
    provenance = _mapping(payload.get("provenance"), "benchmark measurement provenance")
    _required_text(provenance, "source", "benchmark measurement provenance")
    record = {
        "contract_version": CONTRACT_VERSION,
        "record_type": "benchmark_measurements",
        "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "profile": payload.get("profile"),
        "model_name": model_name,
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "suite": {
            "name": suite_name,
            "version": suite_version,
            "kind": kind,
            "comparability": comparability,
        },
        "runtime": _mapping(payload.get("runtime", {}), "benchmark measurement runtime"),
        "environment": _validate_environment(payload.get("environment", {})),
        "decoding": _validate_decoding(payload.get("decoding", {})),
        "runs": runs,
        "summary": summarize_runs(runs, kind=kind, comparable=bool(comparability)),
        "provenance": {str(key): value for key, value in provenance.items()},
        "source_path": source,
    }
    record["benchmark_kind"] = record["summary"]["benchmark_kind"]
    _reject_secret_material(record, "benchmark measurement")
    return record


def import_measurement_record(
    workspace: Path,
    path: Path,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    record = validate_measurement_record(_read_mapping(path), source=str(path))
    root = workspace / ".aiplane" / "benchmarks"
    safe_model = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in record["model_name"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = root / f"{timestamp}-{safe_model}-imported.json"
    result = {
        "name": "benchmark_measurement_import",
        "dry_run": dry_run,
        "source": str(path),
        "destination": str(destination),
        "record": record,
    }
    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)
        atomic_write_text(destination, json.dumps(record, indent=2))
        result["written"] = True
    else:
        result["written"] = False
    return result


def summarize_runs(runs: list[dict[str, Any]], *, kind: str, comparable: bool) -> dict[str, Any]:
    passed_values = [run.get("passed") for run in runs if isinstance(run.get("passed"), bool)]
    scores = [_finite(run.get("score")) for run in runs]
    scores = [value for value in scores if value is not None]
    quality = [_finite(run.get("quality_score")) for run in runs]
    quality = [value for value in quality if value is not None]
    performance = [_finite(run.get("performance_score")) for run in runs]
    performance = [value for value in performance if value is not None]
    elapsed = [_finite(run.get("elapsed_ms")) for run in runs]
    elapsed = [value for value in elapsed if value is not None]
    ttft = [_finite(run.get("ttft_ms")) for run in runs]
    ttft = [value for value in ttft if value is not None]
    throughput = [_finite(run.get("tokens_per_second")) for run in runs]
    throughput = [value for value in throughput if value is not None]
    benchmark_kind = (
        f"comparable_{kind}" if comparable and kind in {"quality", "performance", "mixed"} else f"local_{kind}"
    )
    summary: dict[str, Any] = {
        "benchmark_kind": benchmark_kind,
        "sample_count": len(runs),
        "previewed": sum(run.get("passed") is None for run in runs),
        "passed": sum(value is True for value in passed_values),
        "failed": sum(value is False for value in passed_values),
        "pass_rate": round(sum(value is True for value in passed_values) / len(passed_values), 4)
        if passed_values
        else None,
        "average_score": _mean(scores) or 0,
        "quality_score": _mean(quality),
        "quality_median": _median(quality),
        "quality_stdev": _stdev(quality),
        "performance_score": _mean(performance),
        "performance_median": _median(performance),
        "performance_stdev": _stdev(performance),
        "average_elapsed_ms": _mean(elapsed),
        "median_elapsed_ms": _median(elapsed),
        "average_ttft_ms": _mean(ttft),
        "median_ttft_ms": _median(ttft),
        "average_tokens_per_second": _mean(throughput),
        "median_tokens_per_second": _median(throughput),
    }
    if len(quality) > 1:
        summary["quality_standard_error"] = round(statistics.stdev(quality) / math.sqrt(len(quality)), 4)
    if len(performance) > 1:
        summary["performance_standard_error"] = round(statistics.stdev(performance) / math.sqrt(len(performance)), 4)
    return summary


def benchmark_record_from_runs(
    *,
    profile: str,
    model_name: str,
    provider: object,
    model: object,
    suite: dict[str, Any],
    runtime: dict[str, Any],
    environment: dict[str, Any],
    runs: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    kind = str(suite["kind"])
    comparability = suite.get("comparability")
    summary = summarize_runs(runs, kind=kind, comparable=bool(comparability))
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": "benchmark_measurements",
        "benchmark_kind": summary["benchmark_kind"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "model_name": model_name,
        "provider": provider,
        "model": model,
        "suite": {
            "name": suite["name"],
            "version": suite["version"],
            "kind": kind,
            "comparability": comparability,
        },
        "runtime": runtime,
        "environment": environment,
        "decoding": suite.get("decoding", {}),
        "dry_run": dry_run,
        "runs": runs,
        "results": runs,
        "summary": summary,
        "provenance": {
            "source": "aiplane_benchmark_runner",
            "suite_source": suite.get("source"),
        },
    }


def _validate_run(raw: object, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"benchmark run {index} must be a mapping")
    task = _required_text(raw, "task", f"benchmark run {index}")
    repeat_index = _bounded_int(raw.get("repeat_index", index + 1), f"benchmark run {index} repeat_index", minimum=1)
    passed = raw.get("passed")
    if passed is not None and not isinstance(passed, bool):
        raise ValueError(f"benchmark run {index} passed must be true, false, or null")
    result: dict[str, Any] = {
        "task": task,
        "name": str(raw.get("name") or task),
        "repeat_index": repeat_index,
        "passed": passed,
        "error": str(raw.get("error")) if raw.get("error") is not None else None,
    }
    score = _finite(raw.get("score"))
    if score is not None and not 0 <= score <= 100:
        raise ValueError(f"benchmark run {index} score must be between 0 and 100")
    result["score"] = score
    for field in METRICS:
        value = _finite(raw.get(field))
        if value is None:
            result[field] = None
            continue
        if field.endswith("_score") and not 0 <= value <= 100:
            raise ValueError(f"benchmark run {index} {field} must be between 0 and 100")
        if not field.endswith("_score") and value < 0:
            raise ValueError(f"benchmark run {index} {field} must be non-negative")
        result[field] = value
    result["seed"] = _optional_int(raw.get("seed"), f"benchmark run {index} seed")
    telemetry_source = raw.get("telemetry_source")
    if telemetry_source is not None and (not isinstance(telemetry_source, str) or not telemetry_source.strip()):
        raise ValueError(f"benchmark run {index} telemetry_source must be a non-empty string or null")
    result["telemetry_source"] = telemetry_source
    result["metadata"] = _mapping(raw.get("metadata", {}), f"benchmark run {index} metadata")
    return result


def _validate_evaluator(task: dict[str, Any], allow_commands: bool, task_name: str) -> dict[str, Any]:
    raw = task.get("evaluator")
    if raw is None:
        return {"type": "expected_terms"}
    evaluator = _mapping(raw, f"task {task_name!r} evaluator")
    evaluator_type = str(evaluator.get("type") or ("command" if evaluator.get("command") else "expected_terms"))
    if evaluator_type not in EVALUATOR_TYPES:
        raise ValueError(f"task {task_name!r} evaluator type must be one of: {', '.join(sorted(EVALUATOR_TYPES))}")
    if evaluator_type == "exact_match" and not isinstance(evaluator.get("expected"), str):
        raise ValueError(f"task {task_name!r} exact_match evaluator requires expected text")
    if evaluator_type == "regex":
        pattern = evaluator.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"task {task_name!r} regex evaluator requires a non-empty pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"task {task_name!r} regex evaluator pattern is invalid: {exc}") from exc
    if evaluator_type == "json":
        _string_list(evaluator.get("required_keys", []), f"task {task_name!r} evaluator required_keys")
    if evaluator_type == "command":
        if not allow_commands:
            raise ValueError(f"task {task_name!r} command evaluator requires allow_command_evaluators: true")
        command = evaluator.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError(f"task {task_name!r} command evaluator requires a non-empty string list")
    result = {str(key): value for key, value in evaluator.items()}
    result["type"] = evaluator_type
    return result


def _validate_decoding(raw: object) -> dict[str, Any]:
    value = _mapping(raw, "benchmark decoding")
    result: dict[str, Any] = {}
    for field, minimum, maximum in (
        ("temperature", 0.0, 2.0),
        ("top_p", 0.0, 1.0),
    ):
        if field in value:
            number = _finite(value[field])
            if number is None or not minimum <= number <= maximum:
                raise ValueError(f"benchmark decoding {field} must be between {minimum:g} and {maximum:g}")
            result[field] = number
    if "seed" in value:
        result["seed"] = _optional_int(value["seed"], "benchmark decoding seed")
    if "max_output_tokens" in value:
        result["max_output_tokens"] = _bounded_int(
            value["max_output_tokens"], "benchmark decoding max_output_tokens", minimum=1
        )
    return result


def _validate_comparability(raw: object) -> dict[str, Any] | None:
    if raw in (None, {}):
        return None
    value = _mapping(raw, "benchmark comparability")
    group = _required_text(value, "group", "benchmark comparability")
    return {
        "group": group,
        "protocol": str(value.get("protocol") or ""),
        "requirements": _string_list(value.get("requirements", []), "benchmark comparability requirements"),
    }


def _validate_environment(raw: object) -> dict[str, Any]:
    value = _mapping(raw, "benchmark measurement environment")
    fingerprint = value.get("fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        raise ValueError("benchmark environment fingerprint must be a string")
    return {
        "fingerprint": fingerprint,
        "hardware": _mapping(value.get("hardware", {}), "benchmark environment hardware"),
        "software": _mapping(value.get("software", {}), "benchmark environment software"),
    }


def _read_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text) if path.suffix.lower() == ".json" else parse_yaml(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping/object")
    return payload


def _mapping(value: object, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping/object")
    return value


def _required_text(value: dict[str, Any], field: str, label: str) -> str:
    text = str(value.get(field) or "").strip()
    if not text:
        raise ValueError(f"{label} {field} is required")
    return text


def _string_list(value: object, label: str) -> list[str]:
    if value in (None, []):
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{label} must be a list of non-empty strings")
    result = [item.strip() for item in value]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _bounded_int(
    value: object,
    label: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if number < minimum or maximum is not None and number > maximum:
        suffix = f" and no more than {maximum}" if maximum is not None else ""
        raise ValueError(f"{label} must be at least {minimum}{suffix}")
    return number


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _bounded_int(value, label, minimum=-(2**63), maximum=2**63 - 1)


def _finite(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _stdev(values: list[float]) -> float | None:
    return round(statistics.stdev(values), 4) if len(values) > 1 else None


def _reject_secret_material(value: Any, label: str) -> None:
    forbidden = {"api_key", "token", "password", "secret", "authorization", "credential", "credentials"}
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in forbidden or normalized.endswith(("_api_key", "_token", "_password", "_secret")):
                if child not in (None, "", [], {}):
                    raise ValueError(f"secret-bearing field is forbidden in {label}: {key}")
            _reject_secret_material(child, label)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_material(child, label)
    elif isinstance(value, str) and contains_secret(value):
        raise ValueError(f"secret material is forbidden in {label}")
