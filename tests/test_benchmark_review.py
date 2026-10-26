from __future__ import annotations

import copy
import json
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from aiplane.backends import BackendResult
from aiplane.benchmark_evidence import import_measurement_record, validate_measurement_record
from aiplane.benchmark_review import answer_artifact, export_review, import_review
from aiplane.benchmarks import BenchmarkRunner
from aiplane.cli import main as cli_main
from aiplane.config import load_profile

EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "examples" / "task-evaluation"


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def record(output: str = "4", model: str = "fixture-analysis-small") -> dict:
    return {
        "contract_version": "1.0",
        "record_type": "benchmark_measurements",
        "model_name": model,
        "suite": {"name": "arithmetic", "version": "1", "kind": "quality"},
        "runs": [
            {
                "task": "answer",
                "repeat_index": 1,
                "passed": True,
                "quality_score": 100,
                "artifact": answer_artifact("Two plus two?", output),
            }
        ],
        "provenance": {"source": "synthetic-fixture", "tool_version": "1"},
    }


def inputs(tmp_path: Path):
    source = write(tmp_path / "source.json", record())
    rubric = write(
        tmp_path / "rubric.json",
        {"name": "correctness", "version": "1", "instructions": "Score accuracy.", "score_min": 0, "score_max": 5},
    )
    return source, rubric


def completed(review: dict) -> dict:
    review = copy.deepcopy(review)
    review.update(reviewer="reviewer-A", reviewed_at="2026-10-18T10:00:00+00:00")
    for judgment in review["judgments"]:
        judgment.update({"score": 4, "passed": True} if "score" in judgment else {"preference": "tie"})
    return review


def test_export_import_preview_and_separate_automatic_scores(tmp_path: Path):
    source, rubric = inputs(tmp_path)
    output = tmp_path / "review.json"
    preview = export_review([source], rubric, output)
    assert not preview["written"] and not output.exists()
    export_review([source], rubric, output, dry_run=False)
    with pytest.raises(ValueError, match="overwrite"):
        export_review([source], rubric, output, dry_run=False)
    review = completed(json.loads(output.read_text()))
    write(output, review)
    preview = import_review(tmp_path, output, [source], rubric)
    assert not preview["written"] and not (tmp_path / ".aiplane").exists()
    result = import_review(tmp_path, output, [source], rubric, dry_run=False)
    assert json.loads(Path(result["destination"]).read_text()) == review
    assert json.loads(source.read_text())["runs"][0]["quality_score"] == 100
    assert result["judgment_count"] == 1


@pytest.mark.parametrize("change", ["output", "prompt", "setup", "rubric", "record", "item"])
def test_changed_source_output_setup_and_rubric_refused(tmp_path: Path, change: str):
    source, rubric = inputs(tmp_path)
    review = completed(export_review([source], rubric, tmp_path / "unused.json")["review"])
    raw = json.loads(source.read_text())
    if change in {"output", "prompt"}:
        artifact = raw["runs"][0]["artifact"]
        artifact[change] += " edited"
        raw["runs"][0]["artifact"] = answer_artifact(artifact["prompt"], artifact["output"])
        write(source, raw)
    elif change == "setup":
        raw["runtime"] = {"version": "different"}
        write(source, raw)
    elif change == "rubric":
        value = json.loads(rubric.read_text())
        value["instructions"] = "Different criteria."
        write(rubric, value)
    elif change == "record":
        review["records"][0]["model_name"] = "different"
    else:
        review["items"][0]["output"] = "edited"
    with pytest.raises(ValueError, match="identity mismatch"):
        import_review(tmp_path, write(tmp_path / "completed.json", review), [source], rubric)
    assert not (tmp_path / ".aiplane").exists()


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "score", "nan", "bool", "passed", "reviewer", "timestamp", "extra"]
)
def test_invalid_judgments_fail_before_writes(tmp_path: Path, mutation: str):
    source, rubric = inputs(tmp_path)
    review = completed(export_review([source], rubric, tmp_path / "unused.json")["review"])
    judgment = review["judgments"][0]
    if mutation == "missing":
        judgment.update(score=None, passed=None)
    elif mutation == "duplicate":
        review["judgments"].append(copy.deepcopy(judgment))
    elif mutation == "score":
        judgment["score"] = 6
    elif mutation == "nan":
        judgment["score"] = float("nan")
    elif mutation == "bool":
        judgment["score"] = True
    elif mutation == "passed":
        judgment["passed"] = "yes"
    elif mutation == "reviewer":
        review["reviewer"] = ""
    elif mutation == "timestamp":
        review["reviewed_at"] = "2026-10-18"
    else:
        judgment["unrecognized"] = "field"
    with pytest.raises(ValueError):
        import_review(tmp_path, write(tmp_path / "review.json", review), [source], rubric, dry_run=False)
    assert not (tmp_path / ".aiplane").exists()


@pytest.mark.parametrize("preference", ["left", "right", "tie", "abstain"])
def test_pairwise_judgments_remain_preferences(tmp_path: Path, preference: str):
    left, rubric = inputs(tmp_path)
    right = write(tmp_path / "right.json", record("Four", "other"))
    review = completed(export_review([left, right], rubric, tmp_path / "unused.json", mode="pairwise")["review"])
    review["judgments"][0]["preference"] = preference
    path = write(tmp_path / "review.json", review)
    result = import_review(tmp_path, path, [left, right], rubric, dry_run=False)
    assert result["review"]["judgments"][0]["preference"] == preference
    assert "score" not in result["review"]["judgments"][0]
    review["judgments"][0]["left"] = "wrong"
    write(path, review)
    with pytest.raises(ValueError, match="references"):
        import_review(tmp_path, path, [left, right], rubric)


@pytest.mark.parametrize("mutation", ["dry_run", "error", "missing_artifact", "hash", "duplicate_run"])
def test_unreviewable_records_refused(tmp_path: Path, mutation: str):
    source, rubric = inputs(tmp_path)
    raw = json.loads(source.read_text())
    if mutation == "dry_run":
        raw["dry_run"] = True
    elif mutation == "error":
        raw["runs"][0]["error"] = "provider unavailable"
    elif mutation == "missing_artifact":
        raw["runs"][0].pop("artifact")
    elif mutation == "hash":
        raw["runs"][0]["artifact"]["output"] = "tampered"
    else:
        raw["runs"].append(copy.deepcopy(raw["runs"][0]))
    write(source, raw)
    with pytest.raises(ValueError):
        export_review([source], rubric, tmp_path / "review.json", dry_run=False)
    assert not (tmp_path / "review.json").exists()


def test_pairwise_requires_same_prompts_and_distinct_records(tmp_path: Path):
    source, rubric = inputs(tmp_path)
    other = record("different", "other")
    other["runs"][0]["artifact"] = answer_artifact("Different input", "answer")
    right = write(tmp_path / "right.json", other)
    with pytest.raises(ValueError, match="identical prompts"):
        export_review([source, right], rubric, tmp_path / "review.json", mode="pairwise")
    with pytest.raises(ValueError, match="duplicate source"):
        export_review([source, source], rubric, tmp_path / "review.json", mode="pairwise")


def test_external_grader_retains_native_report_and_importable_data(tmp_path: Path):
    destination = tmp_path / "external"
    run = subprocess.run(
        [
            sys.executable,
            str(EXAMPLES / "evaluate.py"),
            str(EXAMPLES / "answers-fixture.json"),
            "--model",
            "fixture-analysis-small",
            "--output-dir",
            str(destination),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(run.stdout) == {"passed": 18, "total": 20}
    raw = json.loads((destination / "native-results.json").read_text())
    assert raw["version"] == "1.0" and len(raw["cases"]) == 20
    imported = import_measurement_record(tmp_path, destination / "measurements.json", dry_run=False)
    assert imported["record"]["summary"]["quality_score"] == 90
    assert all(row["client_elapsed_ms"] is None for row in imported["record"]["runs"])
    assert all("artifact" in row for row in imported["record"]["runs"])
    source = Path(imported["destination"])
    review = completed(export_review([source], EXAMPLES / "rubric.json", tmp_path / "unused.json")["review"])
    for judgment in review["judgments"]:
        judgment["score"] = 1
    assert (
        import_review(tmp_path, write(tmp_path / "review.json", review), [source], EXAMPLES / "rubric.json")[
            "judgment_count"
        ]
        == 20
    )


def test_native_repeats_retain_answers_and_continue_after_grader_timeout(tmp_path: Path, monkeypatch):
    runner = BenchmarkRunner(load_profile("local-dev", tmp_path))
    suite = json.loads((EXAMPLES / "suite.json").read_text())
    suite["tasks"] = {"case-01": suite["tasks"]["case-01"]}
    suite["tasks"]["case-01"]["evaluator"]["command"] = [
        sys.executable,
        str(EXAMPLES / "grade.py"),
        "{output_file}",
        "billing",
        "false",
    ]
    spec = write(tmp_path / "suite.json", suite)
    answers = iter(['{"category":"billing","urgent":false}', '{"category":"access","urgent":false}'])
    monkeypatch.setattr(runner.catalog, "complete", lambda *a, **kw: BackendResult("synthetic", next(answers)))
    result = runner.run("fixture-analysis-small", task="all", spec_path=spec, repeats=2, environment_mode="system")
    assert [row["passed"] for row in result["runs"]] == [True, False]
    assert [row["artifact"]["output"] for row in result["runs"]] == [
        '{"category":"billing","urgent":false}',
        '{"category":"access","urgent":false}',
    ]
    assert not list((tmp_path / ".aiplane" / "benchmarks" / "work").iterdir())
    normalized = validate_measurement_record(json.loads(Path(result["saved_to"]).read_text()))
    assert normalized["runs"][0]["evaluation"]["returncode"] == 0
    monkeypatch.setattr(runner.catalog, "complete", lambda *a, **kw: BackendResult("synthetic", "answer"))
    monkeypatch.setattr(runner.command_runner, "run", lambda *a, **kw: (_ for _ in ()).throw(TimeoutError("timeout")))
    failed = runner.run("fixture-analysis-small", task="all", spec_path=spec, repeats=2, environment_mode="system")
    assert len(failed["runs"]) == 2
    assert all(row["error"].startswith("grader failed:") for row in failed["runs"])
    assert all(row["artifact"]["output"] == "answer" for row in failed["runs"])


def test_cli_preview_and_confirmed_review_roundtrip(tmp_path: Path, monkeypatch):
    source, rubric = inputs(tmp_path)
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "review.json"
    args = [str(path), "--record", str(source), "--rubric", str(rubric)]

    def invoke(command):
        output = StringIO()
        with redirect_stdout(output):
            assert cli_main(command) == 0
        return json.loads(output.getvalue())

    assert not invoke(["benchmarks", "review-export", *args])["written"]
    assert not path.exists()
    assert invoke(["benchmarks", "review-export", *args, "--yes"])["written"]
    write(path, completed(json.loads(path.read_text())))
    assert not invoke(["benchmarks", "review-import", *args])["written"]
    assert invoke(["benchmarks", "review-import", *args, "--yes"])["written"]


@pytest.mark.parametrize(
    "grade_result,returncode,expected_score,error",
    [
        ({"score": 82.5, "passed": True}, 0, 82.5, False),
        ({"passed": False}, 0, 0, False),
        ({"score": 100, "passed": True}, 2, 100, True),
        ({"score": 101}, 0, 0, True),
        ({"score": float("nan")}, 0, 0, True),
        ({"score": True}, 0, 0, True),
        ({"score": 90, "passed": "false"}, 0, 0, True),
        ({"score": 90, "quality_score": -1}, 0, 0, True),
    ],
)
def test_command_grade_values_and_exit_failures(
    tmp_path: Path, monkeypatch, grade_result, returncode, expected_score, error
):
    from types import SimpleNamespace

    runner = BenchmarkRunner(load_profile("local-dev", tmp_path))
    suite = json.loads((EXAMPLES / "suite.json").read_text())
    suite["tasks"] = {"case-01": suite["tasks"]["case-01"]}
    spec = write(tmp_path / "suite.json", suite)
    monkeypatch.setattr(runner.catalog, "complete", lambda *a, **kw: BackendResult("synthetic", "answer"))
    monkeypatch.setattr(
        runner.command_runner,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout=json.dumps(grade_result), stderr="", returncode=returncode),
    )
    row = runner.run("fixture-analysis-small", task="all", spec_path=spec, save=False, environment_mode="system")[
        "runs"
    ][0]
    assert row["score"] == expected_score
    assert bool(row["error"]) is error
    if error:
        assert not row["passed"]
    assert row["artifact"]["output"] == "answer"


def test_review_rejects_secret_material_before_export(tmp_path: Path):
    source, rubric = inputs(tmp_path)
    raw = json.loads(source.read_text())
    raw["runs"][0]["artifact"] = answer_artifact("input", "Bearer " + "x" * 30)
    write(source, raw)
    with pytest.raises(ValueError, match="secret"):
        export_review([source], rubric, tmp_path / "review.json", dry_run=False)
    assert not (tmp_path / "review.json").exists()
