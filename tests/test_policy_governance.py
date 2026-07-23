from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aiplane.policy import PolicyEngine
from aiplane.policy_state import PolicyGrantStore, parse_duration
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


def _clock(value: datetime):
    return lambda: value


def test_temporary_approval_expires_without_changing_profile_policy(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with _isolated_test_profile(workspace=tmp_path) as source:
        profile = replace(source, tools={**source.tools, "mode": "write_allowed"})
        engine = PolicyEngine(profile, clock=_clock(now))
        assert engine.tool_decision("write_file").outcome == "approval_required"

        record = engine.grants.grant(
            "tool:write_file",
            kind="temporary_approval",
            reason="reviewed maintenance window",
            duration="30m",
        )

        decision = engine.tool_decision("write_file")
        assert decision.outcome == "temporarily_approved"
        assert decision.allowed is True
        assert decision.requires_approval is False
        assert record["reason"] == "reviewed maintenance window"
        assert not (profile.root / "approvals.yaml").read_text(encoding="utf-8").startswith("schema_version")

        expired = PolicyEngine(profile, clock=_clock(now + timedelta(minutes=31)))
        assert expired.tool_decision("write_file").outcome == "approval_required"
        assert expired.drift()["findings"][0]["kind"] == "expired"


def test_override_is_action_scoped_and_drift_detects_stale_grant(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with _isolated_test_profile(workspace=tmp_path) as source:
        restricted = replace(
            source,
            repository={**source.repository, "allowed_providers": ["ollama"]},
        )
        engine = PolicyEngine(restricted, clock=_clock(now))
        assert engine.provider_decision("openai").outcome == "blocked"
        engine.grants.grant(
            "provider:openai",
            kind="override",
            reason="approved hosted evaluation",
            duration="8h",
        )

        assert engine.provider_decision("openai").outcome == "overridden"
        assert engine.provider_decision("anthropic").outcome == "blocked"

        relaxed = replace(
            source,
            repository={**source.repository, "allowed_providers": ["ollama", "openai"]},
        )
        drift = PolicyEngine(relaxed, clock=_clock(now)).drift()
        assert drift["ok"] is False
        assert drift["findings"] == [
            {
                "id": engine.grants.list()[0]["id"],
                "action": "provider:openai",
                "kind": "stale",
                "reason": "action is no longer blocked",
            }
        ]


def test_provider_and_cloud_grants_do_not_leak_into_model_decisions(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with _isolated_test_profile(workspace=tmp_path) as source:
        provider_restricted = replace(
            source,
            repository={**source.repository, "allowed_providers": ["ollama"]},
            models={
                "models": {
                    "local-openai": {
                        "provider": "openai",
                        "model": "local-openai",
                        "local": True,
                        "enabled": True,
                    }
                }
            },
        )
        provider_engine = PolicyEngine(provider_restricted, clock=_clock(now))
        provider_model_base = provider_engine.explain_base("model:local-openai")
        provider_engine.grants.grant(
            "provider:openai",
            kind="override",
            reason="provider-only exception",
            duration="30m",
        )

        assert provider_engine.provider_decision("openai").outcome == "overridden"
        assert provider_engine.model_decision("local-openai") == provider_model_base
        assert provider_engine.explain_base("model:local-openai") == provider_model_base

        cloud_restricted = replace(
            source,
            repository={
                **source.repository,
                "allowed_providers": ["openai"],
                "allow_cloud": False,
            },
            models={
                "models": {
                    "remote-openai": {
                        "provider": "openai",
                        "model": "remote-openai",
                        "local": False,
                        "enabled": True,
                    }
                }
            },
        )
        cloud_engine = PolicyEngine(cloud_restricted, clock=_clock(now))
        cloud_model_base = cloud_engine.explain_base("model:remote-openai")
        cloud_engine.grants.grant(
            "backend:cloud",
            kind="override",
            reason="cloud-only exception",
            duration="30m",
        )

        assert cloud_engine.cloud_decision().outcome == "overridden"
        assert cloud_engine.model_decision("remote-openai") == cloud_model_base
        assert cloud_engine.explain_base("model:remote-openai") == cloud_model_base


def test_policy_state_rejects_malformed_data_and_policy_fails_closed(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        store = PolicyGrantStore(profile)
        store.path.parent.mkdir(parents=True)
        store.path.write_text('{"schema_version": "1.0", "grants": "bad"}', encoding="utf-8")

        with pytest.raises(ValueError, match="grants must be a list"):
            store.list()
        decision = PolicyEngine(profile).provider_decision("ollama")
        assert decision.allowed is False
        assert decision.matched_rule == "policy.local_state"

        store.path.write_text(
            '{"schema_version": "1.0", "profile": "another-profile", "grants": []}',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="different profile"):
            store.list()
        decision = PolicyEngine(profile).provider_decision("ollama")
        assert decision.allowed is False
        assert decision.matched_rule == "policy.local_state"


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("30m", 1800), ("8h", 28800), ("7d", 604800)],
)
def test_policy_duration_parser_is_explicit(value: str, seconds: int) -> None:
    assert parse_duration(value).total_seconds() == seconds


@pytest.mark.parametrize("value", ["", "0m", "1w", "-2h", "soon"])
def test_policy_duration_parser_rejects_ambiguous_values(value: str) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        parse_duration(value)


def test_policy_grant_revoke_round_trip_is_atomic_json(tmp_path: Path) -> None:
    now = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    with _isolated_test_profile(workspace=tmp_path) as source:
        profile = replace(source, tools={**source.tools, "mode": "write_allowed"})
        store = PolicyGrantStore(profile, clock=_clock(now))
        created = store.grant(
            "tool:write_file",
            kind="temporary_approval",
            reason="reviewed change",
            duration="30m",
        )
        payload = json.loads(store.path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["profile"] == profile.name
        assert store.revoke(created["id"])["id"] == created["id"]
        assert store.list() == []


def test_policy_grant_list_drift_and_revoke_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        common = ["--profiles-dir", str(profiles_dir), "policy"]
        granted = run_cli(
            [
                *common,
                "grant",
                "--action",
                "tool:write_file",
                "--reason",
                "reviewed CLI acceptance",
                "--expires-in",
                "30m",
                "--yes",
            ]
        )
        assert granted.code == 0
        grant = json.loads(granted.stdout)["grant"]

        listed = run_cli([*common, "list", "--active-only"])
        assert listed.code == 0
        assert [row["id"] for row in json.loads(listed.stdout)["grants"]] == [grant["id"]]

        drift = run_cli([*common, "drift"])
        assert drift.code == 0
        assert json.loads(drift.stdout)["findings"] == []

        revoked = run_cli([*common, "revoke", grant["id"], "--yes"])
        assert revoked.code == 0
        assert json.loads(revoked.stdout)["revoked"]["id"] == grant["id"]
        assert json.loads(run_cli([*common, "list"]).stdout)["grants"] == []
