from __future__ import annotations

import json
from pathlib import Path

from aiplane.agent_guardrails import BudgetExceeded, GuardrailAdapter, render_guardrails
from aiplane.model_handoff import ModelHandoffManager, validate_handoff_file
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def test_handoff_plan_composes_existing_read_only_decisions(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        plan = ModelHandoffManager(profile).plan(
            role="chat", model="fixture-chat-small", runtime="ollama", context_tokens=1024
        )
    assert plan["record_type"] == "model_handoff"
    assert plan["render_only"] is True
    assert plan["calibration_evidence"]["status"] == "unavailable"
    assert plan["execution_boundary"]["runs_agents"] is False
    assert plan["sha256"].startswith("sha256:")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_handoff_file(profile, path)["valid"] is True
    plan["sha256"] = "sha256:" + "0" * 64
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_handoff_file(profile, path)["valid"] is False


def test_guardrail_receipt_is_opt_in_and_validated(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    contract = render_guardrails(name="bounded", profile="local-dev", framework="simple-openai", limits={})
    adapter = GuardrailAdapter(contract, receipt_path=receipt)
    adapter.before_model_call()
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["record_type"] == "agent_guardrails_receipt"
    assert payload["counters"]["model_calls"] == 1
    limited = GuardrailAdapter(
        render_guardrails(
            name="limited", profile="local-dev", framework="simple-openai", limits={"max_model_calls": 0}
        ),
        receipt_path=receipt,
    )
    try:
        limited.before_model_call()
    except BudgetExceeded:
        pass
    assert json.loads(receipt.read_text(encoding="utf-8"))["enforcement_status"] == "stopped"


def test_handoff_plan_cli_is_render_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        result = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "models",
                "handoff-plan",
                "--role",
                "chat",
                "--model",
                "fixture-chat-small",
                "--runtime",
                "ollama",
            ]
        )
    assert result.code == 0
    assert json.loads(result.stdout)["record_type"] == "model_handoff"


def test_handoff_validate_cli_rejects_tampered_checksum(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        rendered = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "models",
                "handoff-plan",
                "--role",
                "chat",
                "--model",
                "fixture-chat-small",
                "--runtime",
                "ollama",
            ]
        )
        payload = json.loads(rendered.stdout)
        path = tmp_path / "handoff.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        valid = run_cli(["--profiles-dir", str(profiles_dir), "models", "handoff-validate", "handoff.json"])
        payload["sha256"] = "sha256:" + "0" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")
        invalid = run_cli(["--profiles-dir", str(profiles_dir), "models", "handoff-validate", "handoff.json"])
    assert valid.code == 0
    assert json.loads(valid.stdout)["valid"] is True
    assert invalid.code == 0
    assert json.loads(invalid.stdout)["valid"] is False
