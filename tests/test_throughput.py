from __future__ import annotations

from unittest.mock import patch

import pytest

from aiplane.backends import OllamaBackend, OpenAICompatibleBackend
from aiplane.benchmark_evidence import summarize_runs, validate_measurement_record
from aiplane.telemetry import rate_from_milliseconds, throughput_rates
from tests.test_benchmark_evidence import _measurement
from tests.test_runtime_parity_contract import _JsonTransport


@pytest.mark.parametrize(
    "server,client,average,sources",
    [
        (50, 40, 45, ["server", "client"]),
        (50, None, 50, ["server"]),
        (None, 40, 40, ["client"]),
        (None, None, None, []),
        (0, 40, 20, ["server", "client"]),
        (0, None, 0, ["server"]),
        (None, 0, 0, ["client"]),
        (0, 0, 0, ["server", "client"]),
        (float("nan"), 40, 40, ["client"]),
        (50, float("inf"), 50, ["server"]),
    ],
)
def test_available_source_average_does_not_treat_missing_as_zero(server, client, average, sources) -> None:
    rates = throughput_rates(server, client)
    assert rates["average_tokens_per_second"] == average
    assert rates["throughput_average_sources"] == sources


@pytest.mark.parametrize("tokens,duration", [(None, 1000), (8, None), (8, 0), (-1, 1000), (True, 1000)])
def test_client_rate_requires_valid_count_and_positive_interval(tokens, duration) -> None:
    assert rate_from_milliseconds(tokens, duration) is None


def test_endpoint_reports_native_and_observed_rates_for_the_same_response() -> None:
    backend = OllamaBackend(
        http_transport=_JsonTransport({"message": {"content": "ok"}, "eval_count": 100, "eval_duration": 2_000_000_000})
    )
    with patch("aiplane.backends.time.perf_counter", side_effect=[10.0, 12.5]):
        result = backend.chat("model", "prompt")
    assert result.telemetry["server_tokens_per_second"] == 50
    assert result.telemetry["client_tokens_per_second"] == 40
    assert result.telemetry["average_tokens_per_second"] == 45
    assert result.telemetry["client_elapsed_ms"] == 2500
    assert result.telemetry["server_generation_ms"] == 2000


@pytest.mark.parametrize("count,expected", [(100, 40), (0, 0), (None, None)])
def test_usage_only_endpoint_average_uses_its_single_available_rate(count, expected) -> None:
    backend = OpenAICompatibleBackend(
        "https://example.invalid/v1",
        http_transport=_JsonTransport(
            {"choices": [{"message": {"content": "ok"}}], "usage": {"completion_tokens": count}}
        ),
    )
    with patch("aiplane.backends.time.perf_counter", side_effect=[10.0, 12.5]):
        result = backend.chat("model", "prompt")
    assert result.telemetry["server_tokens_per_second"] is None
    assert result.telemetry["client_tokens_per_second"] == expected
    assert result.telemetry["average_tokens_per_second"] == expected


@pytest.mark.parametrize(
    "server,client,average", [(50, 40, 45), (50, None, 50), (None, 40, 40), (None, None, None), (0, None, 0)]
)
def test_import_and_summary_follow_the_available_value_rule(server, client, average) -> None:
    record = _measurement()
    record["runs"] = [{"task": "answer", "server_tokens_per_second": server, "client_tokens_per_second": client}]
    normalized = validate_measurement_record(record)
    assert normalized["runs"][0]["average_tokens_per_second"] == average
    assert normalized["summary"]["average_tokens_per_second"] == average
    assert normalized["summary"]["average_server_tokens_per_second"] == server
    assert normalized["summary"]["average_client_tokens_per_second"] == client


def test_import_rejects_halved_single_source_average() -> None:
    record = _measurement()
    record["runs"] = [{"task": "answer", "server_tokens_per_second": 50, "average_tokens_per_second": 25}]
    with pytest.raises(ValueError, match="mean of available source rates"):
        validate_measurement_record(record)


def test_import_refuses_ambiguous_unlabelled_throughput() -> None:
    record = _measurement()
    record["runs"] = [{"task": "answer", "tokens_per_second": 50}]
    with pytest.raises(ValueError, match="ambiguous"):
        validate_measurement_record(record)


def test_repeated_summary_averages_displayed_source_means_without_imputing_missing_sources() -> None:
    runs = [
        {"server_tokens_per_second": 50, "client_tokens_per_second": 40},
        {"server_tokens_per_second": 30},
        {"client_tokens_per_second": 0},
        {},
    ]
    summary = summarize_runs(runs, kind="performance", comparable=False)
    assert summary["average_tokens_per_second"] == 30  # mean(server mean 40, client mean 20)
    assert summary["median_run_average_tokens_per_second"] == 30
    assert summary["average_server_tokens_per_second"] == 40
    assert summary["average_client_tokens_per_second"] == 20
    assert summary["server_throughput_samples"] == 2
    assert summary["client_throughput_samples"] == 2
