from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from aiplane.cli import main
from aiplane.config import dump_yaml, parse_yaml
from aiplane.ensembles import doctor_ensemble, ensemble_template, load_ensemble, plan_ensemble
from aiplane.harness_catalog import compatibility, harness_catalog
from aiplane.models import Profile


@pytest.fixture
def profile(tmp_path):
    return Profile(
        name="test",
        root=tmp_path,
        workspace=tmp_path,
        hardware={},
        backends={"cloud": {"enabled": True}},
        repository={"allow_cloud": True},
        tools={},
        approvals={},
        environment={},
        targets={},
        models={
            "providers": {"ollama": {"enabled": True}},
            "models": {"coder": {"provider": "ollama", "model": "qwen3:8b", "local": True, "enabled": True}},
        },
    )


def spec():
    return {
        "schema_version": 1,
        "name": "demo",
        "roles": {"coder": {"harness": "opencode", "surface": "cli", "model_alias": "coder", "auth": "none"}},
    }


def test_offline_plan_deterministic_and_secret_free(profile):
    plan = plan_ensemble(spec(), profile)
    assert plan == plan_ensemble(spec(), profile)
    assert plan["roles"]["coder"]["compatibility"]["status"] == "documented"
    assert plan["roles"]["coder"]["binding"]["endpoint"] == "http://localhost:11434"
    assert not plan["execution_ready"]
    assert len(plan["provenance"]["binding_sha256"]) == 64


def test_endpoint_per_role_and_digest_changes(profile):
    original = plan_ensemble(spec(), profile)
    profile.models["models"]["coder"]["endpoint"] = "http://127.0.0.1:1234/v1"
    updated = plan_ensemble(spec(), profile)
    assert updated["provenance"]["binding_sha256"] != original["provenance"]["binding_sha256"]
    assert updated["roles"]["coder"]["binding"]["endpoint"].endswith("1234/v1")


@pytest.mark.parametrize(
    "change",
    [
        {"harness_model": "default"},
        {"model_alias": "not-promoted"},
        {"credential_env": "secret-value"},
        {"guidance": "../outside.md"},
        {"guidance": "/tmp/outside.md"},
        {"api_key": "a-real-secret"},
        {"depends_on": ["missing"]},
        {"depends_on": ["coder"]},
        {"depends_on": ["coder", "coder"]},
        {"surface": "cli\n"},
        {"harness": "imaginary"},
        {"auth": "magic"},
    ],
)
def test_invalid_role_rejected(profile, change):
    data = spec()
    data["roles"]["coder"].update(change)
    with pytest.raises(ValueError):
        plan_ensemble(data, profile)


def test_dependency_order_and_cycle(profile):
    data = spec()
    data["roles"]["planner"] = {**data["roles"]["coder"]}
    data["roles"]["coder"]["depends_on"] = ["planner"]
    assert plan_ensemble(data, profile)["dependency_order"] == ["planner", "coder"]
    data["roles"]["planner"]["depends_on"] = ["coder"]
    with pytest.raises(ValueError, match="cycles"):
        plan_ensemble(data, profile)


def test_symlink_guidance_escape(profile, tmp_path):
    try:
        (tmp_path / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    data = spec()
    data["roles"]["coder"]["guidance"] = "outside/file.md"
    with pytest.raises(ValueError, match="outside"):
        plan_ensemble(data, profile)


@pytest.mark.parametrize(
    "endpoint", ["https://user:password@example.com", "https://example.com/?key=abc", "file:///tmp/model"]
)
def test_credential_and_invalid_endpoints_rejected(profile, endpoint):
    profile.models["models"]["coder"]["endpoint"] = endpoint
    with pytest.raises(ValueError):
        plan_ensemble(spec(), profile)


def test_auth_none_cannot_bypass_remote_auth(profile):
    profile.models["models"]["coder"]["endpoint"] = "https://example.com/v1"
    with pytest.raises(ValueError, match="loopback"):
        plan_ensemble(spec(), profile)


def test_disabled_model_and_provider(profile):
    profile.models["models"]["coder"]["enabled"] = False
    assert plan_ensemble(spec(), profile)["configuration_status"] == "blocked"
    profile.models["providers"]["ollama"]["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        plan_ensemble(spec(), profile)


def test_unknown_protocol_remains_review_only(profile):
    profile.models["models"]["coder"]["protocol"] = "python_library"
    plan = plan_ensemble(spec(), profile)
    assert plan["roles"]["coder"]["compatibility"]["status"] == "unknown"
    assert not plan["execution_ready"]


def test_cursor_direct_endpoint_unsupported(profile):
    data = spec()
    data["roles"]["coder"].update(harness="cursor", auth="product_env", credential_env="CURSOR_API_KEY")
    assert plan_ensemble(data, profile)["configuration_status"] == "blocked"


def test_cursor_native_binding_does_not_invent_provider_endpoint(profile):
    data = spec()
    data["roles"]["coder"] = {
        "harness": "cursor",
        "surface": "sdk",
        "harness_model": "account-model-id",
        "auth": "product_env",
        "credential_env": "CURSOR_API_KEY",
    }
    plan = plan_ensemble(data, profile)
    binding = plan["roles"]["coder"]["binding"]
    assert plan["configuration_status"] == "review_required"
    assert binding["namespace"] == "harness_native"
    assert binding["endpoint"] is None
    assert not plan["execution_ready"]


def test_native_bindings_obey_cloud_policy(profile):
    data = spec()
    data["roles"]["coder"] = {
        "harness": "claude-code",
        "surface": "cli",
        "harness_model": "default",
        "auth": "harness_login",
    }
    blocked = replace(profile, repository={"allow_cloud": False})
    assert plan_ensemble(data, blocked)["configuration_status"] == "blocked"


def test_doctor_observes_presence_without_leaking_or_running(profile, monkeypatch):
    data = spec()
    data["roles"]["coder"].update(auth="provider_env", credential_env="TEST_PROVIDER_KEY")
    monkeypatch.setenv("TEST_PROVIDER_KEY", "super-secret-value")
    monkeypatch.setattr("aiplane.ensembles.shutil.which", lambda _: "/fake/opencode")
    doctor = doctor_ensemble(plan_ensemble(data, profile), profile)
    assert doctor["observations"]["coder"]["credential_env_present"] is True
    assert "super-secret-value" not in json.dumps(doctor)
    assert doctor["observations"]["coder"]["endpoint_health"] == "not_checked"


def test_load_json_duplicate_fields_and_yaml_template(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text('{"name":"a","name":"b"}')
    with pytest.raises(ValueError, match="duplicate"):
        load_ensemble(path)
    assert parse_yaml(dump_yaml(ensemble_template())) == ensemble_template()


def test_catalog_sources_and_cli_without_profile(capsys):
    assert main(["harnesses", "list"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog == harness_catalog()
    assert all(record["sources"] and not record["tested_upstream_versions"] for record in catalog["harnesses"].values())
    assert main(["ensembles", "template"]) == 0
    assert parse_yaml(capsys.readouterr().out) == ensemble_template()


def test_matrix_distinguishes_surface_and_protocol():
    assert compatibility("cursor", "ide", native=True, auth="harness_login")["status"] == "unsupported"
    assert (
        compatibility("codex", "cli", protocol="openai_compatible", provider="ollama", auth="none")["status"]
        == "unknown"
    )
    assert (
        compatibility("claude-code", "cli", protocol="openai_compatible", provider="openai")["status"] == "unsupported"
    )


def test_handoff_schema(profile):
    from jsonschema import Draft202012Validator

    schema = json.loads((Path(__file__).parents[1] / "schemas/aiplane-ensemble-handoff-v1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(plan_ensemble(spec(), profile))


def test_cli_plan_export_doctor_and_blocked_export(profile, tmp_path, monkeypatch, capsys):
    from aiplane import cli_ensembles

    monkeypatch.setattr(cli_ensembles, "load_profile", lambda *a, **k: profile)
    monkeypatch.setattr(cli_ensembles, "resolve_profile_name", lambda *a, **k: profile.name)
    path = tmp_path / "ensemble.json"
    path.write_text(json.dumps(spec()))
    for action, expected in [("plan", 0), ("export", 0), ("doctor", 2)]:
        assert main(["ensembles", action, str(path), "--profile", "test"]) == expected
        assert json.loads(capsys.readouterr().out)["execution_ready"] is False
    profile.models["models"]["coder"]["enabled"] = False
    assert main(["ensembles", "export", str(path), "--profile", "test"]) == 1
    assert "export blocked" in capsys.readouterr().err


@pytest.mark.parametrize(
    "text", ["name: first\nname: second\n", "roles:\n  worker:\n    auth: none\n    auth: provider_env\n"]
)
def test_yaml_duplicate_fields_rejected(tmp_path, text):
    path = tmp_path / "spec.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match="duplicate YAML"):
        load_ensemble(path)
