from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiplane.agent_guardrails import BudgetExceeded, GuardrailAdapter, render_guardrails, validate_guardrails
from aiplane.agents import AgentManager
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def test_adapter_hard_gates_model_token_cost_and_tool_limits() -> None:
    contract = render_guardrails(
        name="bounded",
        profile="local-dev",
        framework="simple-openai",
        limits={"max_model_calls": 1, "max_total_tokens": 5, "max_cost_usd": 0.02, "max_tool_calls": 1},
    )
    adapter = GuardrailAdapter(contract)
    adapter.before_model_call(estimated_input_tokens=2, estimated_cost_usd=0.01)
    adapter.record_model_response(input_tokens=2, output_tokens=2, cost_usd=0.01)
    adapter.before_tool_call()
    with pytest.raises(BudgetExceeded, match="max_model_calls"):
        adapter.before_model_call()


def test_response_overage_is_a_next_call_gate() -> None:
    contract = render_guardrails(
        name="bounded", profile="local-dev", framework="simple-openai", limits={"max_total_tokens": 2}
    )
    adapter = GuardrailAdapter(contract)
    adapter.before_model_call()
    adapter.record_model_response(input_tokens=2, output_tokens=1)
    assert adapter.report()["stop_reason"] == "max_total_tokens"
    with pytest.raises(BudgetExceeded, match="refusing another model call"):
        adapter.before_model_call()


def test_guardrails_validation_rejects_invalid_limit() -> None:
    contract = render_guardrails(name="bounded", profile="local-dev", framework="simple-openai", limits={})
    contract["limits"] = {"max_cost_usd": -1}
    assert "guardrail max_cost_usd must be a non-negative number" in validate_guardrails(contract)


def test_agent_guardrails_render_validate_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        manager = AgentManager(profile)
        contract = manager.guardrails("bounded", framework="simple-openai", model="fixture-chat-small")
        exported = manager.export(
            "bounded", framework="simple-openai", model="fixture-chat-small", file="guardrails.py"
        )
        path = tmp_path / "guardrails.json"
        path.write_text(json.dumps(contract), encoding="utf-8")
        validation = manager.validate_guardrails_file(path)
    assert contract["record_type"] == "agent_guardrails"
    assert validation["valid"] is True
    assert "before_model_call" in exported["content"]


def test_guardrails_cli_renders_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        result = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "agents",
                "guardrails",
                "render",
                "bounded",
                "--framework",
                "simple-openai",
                "--model",
                "fixture-chat-small",
                "--limit",
                "max_total_tokens=123",
                "--rate",
                "input_usd_per_million_tokens=1.25",
            ]
        )
    assert result.code == 0
    payload = json.loads(result.stdout)
    assert payload["record_type"] == "agent_guardrails"
    assert payload["limits"]["max_total_tokens"] == 123
    assert payload["cost"]["rate_card"]["input_usd_per_million_tokens"] == 1.25
