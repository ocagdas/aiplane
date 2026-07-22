from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from aiplane.benchmark_evidence import (
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
    ]
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")
    for name in names:
        payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert name in packaging


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
