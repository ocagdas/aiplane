from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.backends import OllamaBackend, OpenAICompatibleBackend, AnthropicMessagesBackend, AzureOpenAIBackend
from aiplane.benchmark_evidence import validate_measurement_record, validate_suite
from aiplane.benchmarks import BenchmarkRunner
from aiplane.decoding import UnsupportedDecoding, validate_decoding
from tests.boundary_fakes import FakeHttpTransport
from tests.profile_fixtures import _isolated_test_profile


@pytest.mark.parametrize(
    "backend_type,expected",
    [
        (OllamaBackend, {"options": {"temperature": 0, "top_p": 0, "seed": 0, "num_predict": 17}}),
        (OpenAICompatibleBackend, {"temperature": 0, "top_p": 0, "seed": 0, "max_tokens": 17}),
        (AzureOpenAIBackend, {"temperature": 0, "top_p": 0, "seed": 0, "max_tokens": 17}),
        (AnthropicMessagesBackend, {"temperature": 0, "top_p": 0, "max_tokens": 17}),
    ],
)
def test_settings_reach_actual_request_and_submission_evidence(backend_type, expected):
    transport = FakeHttpTransport(
        {"message": {"content": "4"}, "choices": [{"message": {"content": "4"}}], "content": [{"text": "4"}]}
    )
    backend = backend_type("https://synthetic.invalid", http_transport=transport)
    requested = {"temperature": 0, "top_p": 0, "max_output_tokens": 17}
    if backend_type is not AnthropicMessagesBackend:
        requested["seed"] = 0
    result = backend.chat("synthetic-model", "Return 4", decoding=requested)
    wire = json.loads(transport.requests[0][0].data)
    assert {key: wire[key] for key in expected} == expected
    evidence = result.telemetry["decoding_evidence"]
    assert evidence["requested"] == requested
    assert evidence["submitted"] == expected
    assert evidence["status"] == "submitted"
    assert evidence["provider_confirmed"] is None


@pytest.mark.parametrize("requested", [{"seed": 7}, {"temperature": 1.5}])
def test_anthropic_unsupported_settings_refuse_before_network(requested):
    transport = FakeHttpTransport()
    backend = AnthropicMessagesBackend("https://synthetic.invalid", http_transport=transport)
    with pytest.raises(UnsupportedDecoding) as raised:
        backend.chat("model", "prompt", decoding=requested)
    assert transport.requests == []
    assert raised.value.evidence["status"] == "unsupported"
    assert raised.value.evidence["submitted"] == {}


@pytest.mark.parametrize(
    "settings",
    [
        {"unexpected": 1},
        {"seed": 1.5},
        {"seed": None},
        {"seed": True},
        {"max_output_tokens": 0},
        {"max_output_tokens": 2.5},
        {"temperature": float("nan")},
        {"temperature": True},
        {"top_p": 1.1},
    ],
)
def test_invalid_controls_are_never_silently_coerced_or_dropped(settings):
    with pytest.raises(ValueError):
        validate_decoding(settings)


def _spec(tmp_path: Path):
    path = tmp_path / "suite.json"
    suite = {
        "schema_version": "1.0",
        "name": "wire-test",
        "version": "1",
        "kind": "quality",
        "decoding": {"temperature": 0, "seed": 7, "max_output_tokens": 17},
        "tasks": {"answer": {"prompt": "Return 4", "evaluator": {"type": "exact_match", "expected": "4"}}},
    }
    path.write_text(json.dumps(suite))
    return path, suite


def test_runner_catalog_dispatcher_backend_chain_preserves_settings_and_timeout(tmp_path):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        model = profile.models["models"]["fixture-analysis-small"]
        model["provider"] = "synthetic-openai"
        model["ownership"] = "managed_service"
        model.pop("preferred_runtime", None)
        model.pop("supported_runtimes", None)
        profile.models.setdefault("providers", {})["synthetic-openai"] = {
            "protocol": "openai_compatible",
            "endpoint": "http://synthetic.invalid/v1",
        }
        runner = BenchmarkRunner(profile)
        transport = FakeHttpTransport({"choices": [{"message": {"content": "4"}}], "usage": {"completion_tokens": 1}})
        runner.catalog.http_transport = transport
        path, suite = _spec(tmp_path)
        result = runner.run("fixture-analysis-small", task="answer", spec_path=path, timeout_seconds=19, save=False)
        assert result["runs"][0]["error"] is None
        request, timeout = transport.requests[0]
        assert timeout == 19
        wire = json.loads(request.data)
        assert wire["temperature"] == 0 and wire["seed"] == 7 and wire["max_tokens"] == 17
        assert result["runs"][0]["decoding_evidence"]["requested"] == suite["decoding"]
        assert result["runs"][0]["quality_score"] == 100
        normalized = validate_measurement_record(result)
        assert normalized["runs"][0]["decoding_evidence"] == result["runs"][0]["decoding_evidence"]
        assert normalized["suite"]["content_sha256"] == result["suite"]["content_sha256"]
        assert normalized["metric_definitions"] == result["metric_definitions"]
        assert normalized["runs"][0]["task_elapsed_ms"] is not None


def test_workload_digest_changes_with_selected_inputs_and_rubric_but_not_path(tmp_path):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        runner = BenchmarkRunner(profile)
        path, suite = _spec(tmp_path)

        def digest(p):
            return runner.run("fixture-analysis-small", task="answer", spec_path=p, dry_run=True, save=False)["suite"][
                "content_sha256"
            ]

        original = digest(path)
        moved = tmp_path / "moved.json"
        moved.write_text(path.read_text())
        assert digest(moved) == original
        suite["tasks"]["answer"]["prompt"] = "Different input"
        moved.write_text(json.dumps(suite))
        assert digest(moved) != original
        suite["tasks"]["answer"]["prompt"] = "Return 4"
        suite["tasks"]["answer"]["evaluator"]["expected"] = "5"
        moved.write_text(json.dumps(suite))
        assert digest(moved) != original
        assert validate_suite(suite)["decoding"] == suite["decoding"]


def test_provider_rejection_preserves_submission_and_never_retries_without_controls():
    from urllib.error import HTTPError
    from aiplane.decoding import DecodingRejected

    class RejectingTransport:
        def __init__(self):
            self.requests = []

        def open(self, request, *, timeout):
            self.requests.append(request)
            raise HTTPError(request.full_url, 400, "unsupported parameter", {}, None)

    transport = RejectingTransport()
    backend = OpenAICompatibleBackend("https://synthetic.invalid/v1", http_transport=transport)
    with pytest.raises(DecodingRejected) as raised:
        backend.chat("model", "prompt", decoding={"seed": 7})
    assert len(transport.requests) == 1
    assert raised.value.evidence["status"] == "rejected"
    assert raised.value.evidence["submitted"] == {"seed": 7}
    assert raised.value.evidence["http_status"] == 400


def test_unsupported_runner_result_is_saved_as_failure_with_no_invented_telemetry(tmp_path):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        model = profile.models["models"]["fixture-analysis-small"]
        model.update(provider="synthetic-anthropic", ownership="managed_service")
        model.pop("preferred_runtime", None)
        model.pop("supported_runtimes", None)
        profile.models.setdefault("providers", {})["synthetic-anthropic"] = {
            "protocol": "anthropic_api",
            "endpoint": "https://synthetic.invalid",
        }
        runner = BenchmarkRunner(profile)
        transport = FakeHttpTransport()
        runner.catalog.http_transport = transport
        path, _suite = _spec(tmp_path)
        result = runner.run("fixture-analysis-small", task="answer", spec_path=path, save=True)
        assert transport.requests == []
        run = result["runs"][0]
        assert run["passed"] is False
        assert run["decoding_evidence"]["status"] == "unsupported"
        assert run["decoding_evidence"]["unsupported"] == ["seed"]
        assert run["elapsed_ms"] is None and run["average_tokens_per_second"] is None
        assert run["task_elapsed_ms"] >= 0
        assert Path(result["saved_to"]).is_file()
        assert validate_measurement_record(result)["runs"][0]["decoding_evidence"] == run["decoding_evidence"]


def test_preview_does_not_claim_submission_or_measurements(tmp_path):
    with _isolated_test_profile(workspace=tmp_path) as profile:
        runner = BenchmarkRunner(profile)
        transport = FakeHttpTransport()
        runner.catalog.http_transport = transport
        path, _suite = _spec(tmp_path)
        result = runner.run("fixture-analysis-small", task="answer", spec_path=path, dry_run=True, save=False)
        run = result["runs"][0]
        assert transport.requests == []
        assert run["decoding_evidence"]["status"] == "planned"
        assert run["decoding_evidence"]["submitted"] == {}
        assert run["elapsed_ms"] is None
        assert run["task_elapsed_ms"] is None
