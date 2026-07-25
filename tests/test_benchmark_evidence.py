from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from aiplane.benchmark_evidence import (
    export_calibration_bundle,
    import_calibration_bundle,
    import_measurement_record,
    summarize_runs,
    validate_measurement_record,
    validate_suite,
)
from aiplane.benchmarks import BenchmarkRunner
from aiplane.cli import main as cli_main
from aiplane.config import load_profile


def _suite(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "name": "user-quality",
        "version": "2026.1",
        "kind": "quality",
        "repeats": 3,
        "decoding": {"temperature": 0.0, "seed": 7},
        "comparability": {"group": "team-python", "protocol": "fixed-prompts"},
        "metrics": ["quality_score", "elapsed_ms"],
        "tasks": {
            "answer": {
                "prompt": "Return 4.",
                "evaluator": {"type": "exact_match", "expected": "4"},
            }
        },
    }
    payload.update(overrides)
    return payload


def _measurement() -> dict[str, object]:
    return {
        "contract_version": "1.0",
        "record_type": "benchmark_measurements",
        "created_at": "2026-07-22T10:00:00Z",
        "model_name": "fixture-analysis-small",
        "suite": {
            "name": "user-quality",
            "version": "2026.1",
            "kind": "quality",
            "comparability": {"group": "team-python", "protocol": "fixed-prompts"},
        },
        "runtime": {"name": "ollama", "version": "0.9"},
        "environment": {
            "fingerprint": "sha256:synthetic",
            "hardware": {"ram_gb": 32},
            "software": {"os": "test"},
        },
        "decoding": {"temperature": 0.0, "seed": 7},
        "runs": [
            {"task": "answer", "repeat_index": 1, "passed": True, "quality_score": 80, "elapsed_ms": 100},
            {"task": "answer", "repeat_index": 2, "passed": True, "quality_score": 100, "elapsed_ms": 120},
        ],
        "provenance": {"source": "user_lab", "tool_version": "1.2"},
    }


def test_suite_contract_is_versioned_and_command_evaluators_are_opt_in() -> None:
    suite = validate_suite(_suite(), source="test")
    assert suite["repeats"] == 3
    assert suite["tasks"]["answer"]["evaluator"]["type"] == "exact_match"

    command_suite = _suite(
        tasks={
            "answer": {
                "prompt": "Return 4.",
                "evaluator": {"type": "command", "command": ["grader", "{output_file}"]},
            }
        }
    )
    with pytest.raises(ValueError, match="allow_command_evaluators"):
        validate_suite(command_suite)


def test_suite_accepts_native_load_and_prompt_throughput_metrics() -> None:
    suite = validate_suite(
        _suite(metrics=["load_duration_ms", "prompt_tokens_per_second", "tokens_per_second"]), source="test"
    )
    assert suite["metrics"] == ["load_duration_ms", "prompt_tokens_per_second", "tokens_per_second"]


def test_runner_repeats_suite_and_records_uncertainty(tmp_path: Path) -> None:
    profile = load_profile("local-dev", tmp_path)
    result = BenchmarkRunner(profile).run(
        "fixture-analysis-small",
        task="analysis",
        dry_run=True,
        save=False,
        repeats=3,
    )
    assert len(result["runs"]) == 3
    assert [run["repeat_index"] for run in result["runs"]] == [1, 2, 3]
    assert result["summary"]["sample_count"] == 3
    assert result["summary"]["benchmark_kind"] == "local_smoke"
    assert "saved_to" not in result
    assert not (tmp_path / ".aiplane" / "benchmarks").exists()

    with pytest.raises(ValueError, match="between 1 and 100"):
        BenchmarkRunner(profile).run(
            "fixture-analysis-small",
            dry_run=True,
            save=False,
            repeats=0,
        )


def test_user_measurement_import_is_preview_first_and_preserves_provenance(tmp_path: Path) -> None:
    source = tmp_path / "measurements.json"
    source.write_text(json.dumps(_measurement()), encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    preview = import_measurement_record(workspace, source)
    assert preview["dry_run"] is True
    assert preview["written"] is False
    assert not Path(preview["destination"]).exists()
    assert preview["record"]["provenance"]["source"] == "user_lab"
    assert preview["record"]["summary"]["quality_score"] == 90.0
    assert preview["record"]["summary"]["quality_standard_error"] == 10.0

    written = import_measurement_record(workspace, source, dry_run=False)
    assert written["written"] is True
    assert Path(written["destination"]).exists()


def test_controlled_measurement_requires_reproducible_conditions_and_ttft_provenance() -> None:
    controlled = _measurement()
    controlled["calibration"] = {
        "status": "controlled",
        "run_mode": "warm",
        "context_tokens": 8192,
        "concurrency": 1,
        "warmup_runs": 1,
        "power_mode": "performance",
    }
    controlled["runs"][0]["ttft_ms"] = 42
    controlled["runs"][0]["telemetry_source"] = "native_runtime"
    record = validate_measurement_record(controlled)
    assert record["calibration"]["status"] == "controlled"

    missing_source = _measurement()
    missing_source["calibration"] = controlled["calibration"]
    missing_source["runs"][0]["ttft_ms"] = 42
    with pytest.raises(ValueError, match="telemetry_source"):
        validate_measurement_record(missing_source)


def test_calibration_plan_cli_is_read_only_and_requires_a_configured_model() -> None:
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = cli_main(
            [
                "benchmarks",
                "calibration-plan",
                "--model",
                "fixture-analysis-small",
                "--runtime",
                "ollama",
                "--repeats",
                "5",
                "--profile",
                "local-dev",
            ]
        )
    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["record_type"] == "benchmark_calibration_plan"
    assert payload["commands"][0].endswith("--dry-run")
    assert payload["calibration"]["status"] == "controlled"


def test_calibration_bundle_round_trips_only_controlled_records(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    root = workspace / ".aiplane" / "benchmarks"
    root.mkdir(parents=True)
    controlled = _measurement()
    controlled["calibration"] = {
        "status": "controlled",
        "run_mode": "warm",
        "context_tokens": 8192,
        "concurrency": 1,
        "warmup_runs": 1,
        "power_mode": "performance",
    }
    (root / "controlled.json").write_text(json.dumps(controlled), encoding="utf-8")
    (root / "uncontrolled.json").write_text(json.dumps(_measurement()), encoding="utf-8")
    bundle_path = tmp_path / "out" / "calibration.json"

    exported = export_calibration_bundle(workspace, bundle_path, dry_run=False)
    assert exported["record_count"] == 1
    assert bundle_path.exists()
    restored = tmp_path / "restored"
    imported = import_calibration_bundle(restored, bundle_path, dry_run=False)
    assert imported["record_count"] == 1
    assert len(imported["destinations"]) == 1


def test_measurement_contract_rejects_secrets_and_invalid_scores() -> None:
    secret = _measurement()
    secret["provenance"] = {"source": "user_lab", "api_key": "not-allowed-here"}
    with pytest.raises(ValueError, match="secret-bearing"):
        validate_measurement_record(secret)

    invalid = _measurement()
    invalid["runs"][0]["quality_score"] = 101
    with pytest.raises(ValueError, match="between 0 and 100"):
        validate_measurement_record(invalid)


def test_summary_keeps_quality_and_performance_separate() -> None:
    summary = summarize_runs(
        [
            {"passed": True, "quality_score": 70, "performance_score": 90, "elapsed_ms": 20},
            {"passed": False, "quality_score": 50, "performance_score": 80, "elapsed_ms": 40},
        ],
        kind="mixed",
        comparable=True,
    )
    assert summary["benchmark_kind"] == "comparable_mixed"
    assert summary["quality_score"] == 60.0
    assert summary["performance_score"] == 85.0
    assert summary["pass_rate"] == 0.5


def test_public_evidence_schemas_are_declared_for_packaging() -> None:
    root = Path.cwd()
    names = [
        "aiplane-benchmark-suite-v1.schema.json",
        "aiplane-benchmark-measurements-v1.schema.json",
        "aiplane-artifact-lock-v1.schema.json",
        "aiplane-runtime-launch-v1.schema.json",
        "aiplane-runtime-bundle-v1.schema.json",
        "aiplane-agent-environment-v1.schema.json",
        "aiplane-agent-job-v1.schema.json",
        "aiplane-agent-handoff-v1.schema.json",
        "aiplane-deployment-artifacts-v1.schema.json",
        "aiplane-offline-model-catalog-v1.schema.json",
    ]
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")
    for name in names:
        payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert name in packaging

    measurements = json.loads(
        (root / "schemas" / "aiplane-benchmark-measurements-v1.schema.json").read_text(encoding="utf-8")
    )
    run_properties = measurements["properties"]["runs"]["items"]["properties"]
    assert run_properties["telemetry_source"]["type"] == ["string", "null"]

    agent = json.loads((root / "schemas" / "aiplane-agent-environment-v1.schema.json").read_text(encoding="utf-8"))
    assert {"framework", "readiness", "framework_config", "control_enforcement"} <= set(agent["properties"])
    job = json.loads((root / "schemas" / "aiplane-agent-job-v1.schema.json").read_text(encoding="utf-8"))
    assert "control_enforcement" in job["required"]


def test_calibration_bundle_cli_previews_export_and_import(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "calibration.json"
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = cli_main(["benchmarks", "calibration-export", str(bundle), "--profile", "local-dev"])
    assert code == 0
    assert json.loads(stdout.getvalue())["written"] is False


def test_benchmark_contract_cli_validates_and_previews_import(tmp_path: Path) -> None:
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps(_suite()), encoding="utf-8")
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = cli_main(["benchmarks", "suite-validate", str(suite_path)])
    assert code == 0
    assert json.loads(stdout.getvalue())["schema_version"] == "1.0"

    measurement_path = tmp_path / "measurement.json"
    measurement_path.write_text(json.dumps(_measurement()), encoding="utf-8")
    stdout = StringIO()
    with redirect_stdout(stdout):
        code = cli_main(["benchmarks", "import", str(measurement_path)])
    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["dry_run"] is True
    assert payload["written"] is False
