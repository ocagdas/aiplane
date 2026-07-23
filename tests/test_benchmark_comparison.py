from __future__ import annotations

import json
from pathlib import Path

from aiplane.benchmark_comparison import compare_benchmarks
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def _record(runtime: str, *, quality: float, ttft: float, source: str | None) -> dict:
    run = {
        "task": "chat",
        "repeat_index": 1,
        "passed": True,
        "score": quality,
        "quality_score": quality,
        "performance_score": None,
        "elapsed_ms": 100,
        "ttft_ms": ttft,
        "prompt_tokens": 10,
        "output_tokens": 20,
        "tokens_per_second": 40,
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
            "software": {},
        },
        "decoding": {"temperature": 0, "seed": 7},
        "runs": [run],
        "provenance": {"source": "test_lab"},
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
