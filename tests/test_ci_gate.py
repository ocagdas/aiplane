from __future__ import annotations

import json

import pytest

from scripts import ci_gate


@pytest.mark.parametrize("state", [None, "failure", "skipped", "cancelled", "pending", {}, True])
def test_required_results_fail_closed(state):
    results = {name: {"result": "success"} for name in ci_gate.REQUIRED_JOBS}
    results["compatibility"] = {"result": state}
    assert ci_gate.evaluate(results)["go"] is False


def test_missing_malformed_and_additional_failures_block():
    for malformed in (None, [], {}, {"checks": "success"}):
        assert ci_gate.evaluate(malformed)["go"] is False
    results = {name: {"result": "success"} for name in ci_gate.REQUIRED_JOBS}
    assert ci_gate.evaluate(results)["go"] is True
    results["unexpected"] = {"result": "failure"}
    assert ci_gate.evaluate(results)["go"] is False


def test_report_carries_revision_run_and_boolean_output(tmp_path, monkeypatch):
    report = tmp_path / "ci-gate.json"
    output = tmp_path / "outputs"
    monkeypatch.setenv("NEEDS_JSON", json.dumps({name: {"result": "success"} for name in ci_gate.REQUIRED_JOBS}))
    monkeypatch.setenv("GITHUB_SHA", "tested")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert ci_gate.main(["--report", str(report)]) == 0
    data = json.loads(report.read_text())
    assert data == {
        "schema_version": 1,
        "go": True,
        "commit": "tested",
        "run_id": "42",
        "checks": {name: "success" for name in ci_gate.REQUIRED_JOBS},
    }
    assert output.read_text() == "go=true\n"
    monkeypatch.setenv("NEEDS_JSON", "invalid")
    assert ci_gate.main(["--report", str(report)]) == 1
