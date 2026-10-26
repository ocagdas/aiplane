from __future__ import annotations

import json
import copy
import pytest

from aiplane.benchmark_identity import METRIC_DEFINITIONS
from aiplane.decoding import decoding_request
from pathlib import Path

from aiplane.benchmark_comparison import compare_benchmarks
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def _record(runtime: str, *, quality: float, ttft: float, source: str | None) -> dict:
    run = {
        "task": "chat",
        "decoding_evidence": decoding_request("ollama_api", {"temperature": 0, "seed": 7})[1],
        "repeat_index": 1,
        "passed": True,
        "score": quality,
        "quality_score": quality,
        "performance_score": None,
        "elapsed_ms": 100,
        "ttft_ms": ttft if source else None,
        "prompt_tokens": 10,
        "output_tokens": 20,
        "server_tokens_per_second": 40,
        "telemetry_source": source,
    }
    return {
        "contract_version": "1.0",
        "record_type": "benchmark_measurements",
        "created_at": f"2026-07-23T12:00:0{1 if runtime == 'ollama' else 2}+00:00",
        "profile": "local-dev",
        "model_name": "fixture-chat-small",
        "provider": "local",
        "model": "provider-chat:1b",
        "suite": {
            "name": "chat-quality",
            "content_sha256": "a" * 64,
            "version": "1.0",
            "kind": "mixed",
            "comparability": {
                "group": "chat-v1",
                "protocol": "fixed-prompts",
                "requirements": ["same decoding", "same context"],
            },
        },
        "runtime": {
            "name": runtime,
            "version": "test",
            "settings": {"context_tokens": 8192, "quantization": "q4"},
        },
        "environment": {
            "fingerprint": "same-host",
            "hardware": {"name": "test-gpu"},
            "software": {"os": "synthetic-os", "driver": "synthetic-driver"},
        },
        "decoding": {"temperature": 0, "seed": 7},
        "calibration": {
            "status": "controlled",
            "run_mode": "warm",
            "context_tokens": 8192,
            "concurrency": 1,
            "warmup_runs": 1,
            "power_mode": "performance",
        },
        "runs": [run],
        "provenance": {"source": "test_lab"},
        "metric_definitions": METRIC_DEFINITIONS,
        "comparison_context": {
            "workload": {
                "inputs": "sha256:inputs",
                "rubric": "sha256:rubric",
                "prompt": "sha256:prompt",
                "harness": "synthetic-1",
            },
            "model": {"artifact": "sha256:weights", "tokenizer": "sha256:tokenizer"},
            "runtime": {"build": "synthetic-build"},
            "execution": {"route": "direct-runtime", "cache": "disabled", "concurrency": 1, "tools": "none"},
        },
    }


def test_comparison_groups_matching_records_and_keeps_metrics_separate(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "ollama.json").write_text(
            json.dumps(_record("ollama", quality=70, ttft=20, source="ollama_native")), encoding="utf-8"
        )
        (root / "vllm.json").write_text(json.dumps(_record("vllm", quality=90, ttft=10, source=None)), encoding="utf-8")

        result = compare_benchmarks(profile, by="runtime")

    assert result["records_matched"] == 2
    assert len(result["groups"]) == 1
    group = result["groups"][0]
    assert group["comparison_ready"] is True
    assert group["leaders"]["quality_score"]["runtime"] == "vllm"
    assert group["leaders"]["ttft_ms"]["runtime"] == "ollama"
    assert group["leaders"]["ttft_ms"]["source"] == ["ollama_native"]
    assert "universal_score" not in group["leaders"]


def test_comparison_filters_and_reports_invalid_records_without_failing(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "record.json").write_text(
            json.dumps(_record("ollama", quality=70, ttft=20, source="native")), encoding="utf-8"
        )
        (root / "broken.json").write_text("{", encoding="utf-8")

        excluded = compare_benchmarks(profile, runtimes=["vllm"])
        included = compare_benchmarks(profile, runtimes=["ollama"], suite="chat-quality")

    assert excluded["records_matched"] == 0
    assert included["records_matched"] == 1
    assert included["warnings"] == [{"path": str(root / "broken.json"), "reason": "JSONDecodeError"}]


def test_suite_without_comparability_never_produces_leaders(tmp_path: Path) -> None:
    record = _record("ollama", quality=70, ttft=20, source="native")
    record["suite"]["comparability"] = None
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "local.json").write_text(json.dumps(record), encoding="utf-8")
        group = compare_benchmarks(profile)["groups"][0]

    assert group["comparable"] is False
    assert group["comparison_ready"] is False
    assert group["leaders"] == {}


def test_uncontrolled_records_are_visible_but_cannot_claim_comparison_leaders(tmp_path: Path) -> None:
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = _record("vllm", quality=80, ttft=10, source="native")
    first["calibration"] = {"status": "uncontrolled"}
    second["calibration"] = {"status": "uncontrolled"}
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "first.json").write_text(json.dumps(first), encoding="utf-8")
        (root / "second.json").write_text(json.dumps(second), encoding="utf-8")
        group = compare_benchmarks(profile, by="runtime")["groups"][0]

    assert group["comparison_ready"] is False
    assert "records do not declare controlled calibration" in group["comparison_blockers"]
    assert group["leaders"] == {}


def test_single_comparable_record_does_not_claim_a_leader(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "local.json").write_text(
            json.dumps(_record("ollama", quality=70, ttft=20, source="native")),
            encoding="utf-8",
        )
        group = compare_benchmarks(profile, by="runtime")["groups"][0]

    assert group["comparable"] is True
    assert group["comparison_ready"] is False
    assert group["leaders"] == {}


def test_benchmark_compare_cli_dispatches_filters(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        root = tmp_path / ".aiplane" / "benchmarks"
        root.mkdir(parents=True)
        (root / "ollama.json").write_text(
            json.dumps(_record("ollama", quality=70, ttft=20, source="native")),
            encoding="utf-8",
        )
        result = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "benchmarks",
                "compare",
                "--by",
                "runtime",
                "--model",
                "fixture-chat-small",
                "--runtime",
                "ollama",
            ]
        )

    assert result.code == 0
    payload = json.loads(result.stdout)
    assert payload["dimension"] == "runtime"
    assert payload["filters"]["models"] == ["fixture-chat-small"]
    assert payload["filters"]["runtimes"] == ["ollama"]


def test_throughput_average_with_different_available_sources_is_not_ranked_together(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = profile.workspace / ".aiplane/benchmarks"
        root.mkdir(parents=True, exist_ok=True)
        server_only = _record("ollama", quality=70, ttft=20, source="native")
        both = _record("vllm", quality=80, ttft=30, source="native")
        both["runs"][0]["client_tokens_per_second"] = 20
        for name, record in [("server", server_only), ("both", both)]:
            (root / f"{name}.json").write_text(json.dumps(record))
        result = compare_benchmarks(profile, by="runtime")
        assert len(result["groups"]) == 2
        assert all(not group["comparison_ready"] for group in result["groups"])


def _compare_pair(tmp_path, first, second, *, by="runtime"):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        root = tmp_path / ".aiplane/benchmarks"
        root.mkdir(parents=True, exist_ok=True)
        for name, record in [("first", first), ("second", second)]:
            (root / f"{name}.json").write_text(json.dumps(record))
        return compare_benchmarks(profile, by=by)


@pytest.mark.parametrize(
    "path,value",
    [
        (("suite", "content_sha256"), "different-input-or-rubric"),
        (("comparison_context", "model", "artifact"), "different-weight-revision"),
        (("comparison_context", "model", "tokenizer"), "different-tokenizer"),
        (("comparison_context", "execution", "route"), "proxy"),
        (("comparison_context", "execution", "cache"), "enabled"),
        (("comparison_context", "execution", "concurrency"), 2),
        (("comparison_context", "execution", "tools"), "toolset-v2"),
        (("comparison_context", "workload", "harness"), "harness-v2"),
        (("environment", "software", "driver"), "different-driver"),
        (("environment", "hardware", "name"), "different-gpu"),
        (("metric_definitions", "client_tokens_per_second"), {"unit": "tokens/s", "denominator": "decode-only"}),
    ],
)
def test_non_varied_controls_split_groups(tmp_path, path, value):
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = copy.deepcopy(_record("vllm", quality=80, ttft=10, source="native"))
    node = second
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    result = _compare_pair(tmp_path, first, second)
    assert len(result["groups"]) == 2
    assert all(not group["comparison_ready"] and group["leaders"] == {} for group in result["groups"])


@pytest.mark.parametrize(
    "change,blocker",
    [
        ("model", "unknown comparison_context.model.artifact"),
        ("metrics", "unknown metric_definitions.elapsed_ms"),
        ("submission", "requested decoding has no matching submission evidence"),
        ("error", "run contains an execution error"),
        ("preview", "preview is not measured evidence"),
    ],
)
def test_unknown_or_invalid_evidence_is_visible_without_leaders(tmp_path, change, blocker):
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = _record("vllm", quality=80, ttft=10, source="native")
    for record in (first, second):
        if change == "model":
            record["comparison_context"]["model"]["artifact"] = None
        elif change == "metrics":
            record["metric_definitions"] = {}
        elif change == "submission":
            record["runs"][0]["decoding_evidence"]["submitted"] = {"options": {"temperature": 1}}
        elif change == "error":
            record["runs"][0]["error"] = "endpoint failed"
        else:
            record["dry_run"] = True
    if change == "preview":
        with _isolated_test_profile(workspace=tmp_path) as profile:
            root = tmp_path / ".aiplane/benchmarks"
            root.mkdir(parents=True)
            for name, record in [("first", first), ("second", second)]:
                (root / f"{name}.json").write_text(json.dumps(record))
            assert compare_benchmarks(profile)["records_matched"] == 0
            result = compare_benchmarks(profile, include_dry_run=True)
    else:
        result = _compare_pair(tmp_path, first, second)
    assert result["records_matched"] == 2
    group = result["groups"][0]
    assert blocker in group["comparison_blockers"]
    assert group["comparison_ready"] is False and group["leaders"] == {}


def test_model_comparison_holds_runtime_build_and_settings_fixed(tmp_path):
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = copy.deepcopy(first)
    second["model_name"] = "other-alias"
    second["model"] = "different-model"
    second["comparison_context"]["model"] = {"artifact": "different-weights", "tokenizer": "different-tokenizer"}
    assert _compare_pair(tmp_path, first, second, by="model")["groups"][0]["comparison_ready"]
    second["runtime"]["version"] = "different-build"
    result = _compare_pair(tmp_path, first, second, by="model")
    assert len(result["groups"]) == 2
    assert all(not group["comparison_ready"] for group in result["groups"])


def test_same_alias_different_artifacts_are_distinct_models(tmp_path):
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = copy.deepcopy(first)
    second["comparison_context"]["model"]["artifact"] = "other-revision"
    group = _compare_pair(tmp_path, first, second, by="model")["groups"][0]
    assert group["comparison_ready"] is True
    assert group["rows"][0]["varying_identity"] != group["rows"][1]["varying_identity"]


def test_malformed_runtime_settings_become_warning_instead_of_crashing_comparison(tmp_path):
    first = _record("ollama", quality=70, ttft=20, source="native")
    second = _record("vllm", quality=80, ttft=10, source="native")
    second["runtime"]["settings"] = ["invalid"]
    result = _compare_pair(tmp_path, first, second)
    assert result["records_matched"] == 1
    assert len(result["warnings"]) == 1
    assert "runtime settings" in result["warnings"][0]["reason"]
