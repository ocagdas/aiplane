from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aiplane.agent_frameworks import (
    FRAMEWORK_SPECS,
    framework_control_enforcement,
    framework_readiness,
    render_framework_starter,
)
from aiplane.agents import AgentManager
from tests.boundary_fakes import FakeHttpTransport
from aiplane.machines import MachineManager
from aiplane.stacks import StackManager
from aiplane.config import parse_yaml
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile, _load_profile_with_test_models


@pytest.mark.parametrize(
    ("framework", "topology_key"),
    [
        ("langgraph", "graph"),
        ("crewai", "crew"),
        ("autogen", "team"),
        ("semantic_kernel", "kernel"),
        ("llamaindex_workflows", "workflow"),
        ("openhands", "openhands"),
        ("simple-openai", "client"),
    ],
)
def test_framework_starters_have_specific_topology_and_safe_boundaries(framework: str, topology_key: str) -> None:
    content = render_framework_starter(
        framework,
        {
            "name": "review-team",
            "profile": "local-dev",
            "runtime": "ollama",
            "endpoint": "http://localhost:11434/v1",
            "approval_mode": "ask",
            "roles": {
                "planner": {
                    "model_alias": "fixture-chat-small",
                    "model_id": "provider-chat:1b",
                    "runtime": "ollama",
                    "endpoint": "http://localhost:11434/v1",
                    "credential": {"api_key_env": None},
                    "approval_mode": "ask",
                }
            },
        },
    )
    payload = parse_yaml(content)

    assert payload["framework"] == framework
    assert payload["packages"] == FRAMEWORK_SPECS[framework]["packages"]
    assert topology_key in payload["topology"]
    assert payload["readiness"]["ready"] is True
    assert payload["execution_boundary"] == {
        "runs_agents": False,
        "installs_packages": False,
        "writes_credentials": False,
    }
    assert "replace-me" not in content


def test_every_framework_advertises_its_rendered_contract_files(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        templates = AgentManager(profile).templates()

    assert {row["name"] for row in templates} == set(FRAMEWORK_SPECS)
    for row in templates:
        assert {
            "endpoint-smoke.py",
            "endpoint-smoke-requirements.txt",
            "agent-environment.json",
            "agent-environment.yaml",
            "framework-config.yaml",
        } <= set(row["files"])
        assert ("agent.py" in row["files"]) is (row["name"] in {"langgraph", "simple-openai"})


def test_agent_manifest_embeds_framework_readiness_and_rendered_config(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        manifest = AgentManager(profile).manifest(
            "crew-review",
            framework="crewai",
            model="fixture-chat-small",
        )

    config = parse_yaml(manifest["framework_config"])
    assert manifest["record_type"] == "agent_environment"
    assert manifest["framework"]["name"] == "crewai"
    assert manifest["readiness"]["ready"] is True
    assert config["framework"] == "crewai"
    assert config["roles"]["primary"]["model_alias"] == "fixture-chat-small"
    assert manifest["execution_boundary"]["runs_agents"] is False


def test_single_role_framework_reports_multi_role_mismatch() -> None:
    payload = parse_yaml(
        render_framework_starter(
            "openhands",
            {
                "approval_mode": "ask",
                "roles": {
                    "planner": {"model": "a", "model_id": "a", "endpoint": "http://localhost:1"},
                    "reviewer": {"model": "b", "model_id": "b", "endpoint": "http://localhost:2"},
                },
            },
        )
    )
    check = payload["readiness"]["checks"]["multi_role_supported"]
    assert check["ok"] is False
    assert payload["readiness"]["ready"] is False


def test_framework_config_cli_export_is_yaml_and_render_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        result = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "agents",
                "export",
                "review-team",
                "--framework",
                "crewai",
                "--model",
                "fixture-chat-small",
                "--file",
                "framework-config.yaml",
            ]
        )

    assert result.code == 0
    payload = parse_yaml(result.stdout)
    assert payload["framework"] == "crewai"
    assert payload["topology"]["crew"]["agents"] == ["primary"]
    assert payload["execution_boundary"]["runs_agents"] is False


@pytest.mark.parametrize("framework", sorted(FRAMEWORK_SPECS))
def test_every_framework_has_a_compilable_endpoint_smoke_starter(tmp_path: Path, framework: str) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        manager = AgentManager(profile)
        runner = manager.export(
            "endpoint-check", framework=framework, model="fixture-chat-small", file="endpoint-smoke.py"
        )
        smoke_requirements = manager.export(
            "endpoint-check", framework=framework, model="fixture-chat-small", file="endpoint-smoke-requirements.txt"
        )
        requirements = manager.export(
            "endpoint-check", framework=framework, model="fixture-chat-small", file="requirements.txt"
        )
        readme = manager.export("endpoint-check", framework=framework, model="fixture-chat-small", file="README.md")

    compile(runner["content"], "endpoint-smoke.py", "exec")
    assert "from openai import OpenAI" in runner["content"]
    assert smoke_requirements["content"] == "openai\n"
    assert requirements["content"].splitlines() == FRAMEWORK_SPECS[framework]["packages"]
    assert "Verify the endpoint" in readme["content"]
    if framework in {"langgraph", "simple-openai"}:
        assert "python agent.py" in readme["content"]
    else:
        assert "python endpoint-smoke.py" in readme["content"]


def test_framework_readiness_rejects_invalid_endpoint_and_non_chat_model() -> None:
    readiness = framework_readiness(
        "crewai",
        {
            "planner": {
                "model": "fixture",
                "endpoint": "file:///tmp/not-an-api",
                "endpoint_protocol": "openai_compatible",
                "model_roles": ["embedding"],
            }
        },
        "ask",
    )

    assert readiness["ready"] is False
    assert readiness["checks"]["role_endpoint:planner"]["ok"] is False
    assert readiness["checks"]["role_chat_capability:planner"]["ok"] is False


def test_framework_aware_default_export_is_runnable_for_config_targets(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        exported = AgentManager(profile).export("crew-check", framework="crewai", model="fixture-chat-small")

    assert exported["file"] == "endpoint-smoke.py"
    compile(exported["content"], "endpoint-smoke.py", "exec")


def test_agent_selection_rejects_non_http_endpoint_override(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        manager = AgentManager(profile)
        with pytest.raises(ValueError, match="must use http or https"):
            manager.plan("endpoint-check", framework="crewai", model="fixture-chat-small", endpoint="file:///tmp/model")


def test_agent_doctor_is_offline_by_default_and_never_reads_credentials(tmp_path: Path) -> None:
    transport = FakeHttpTransport()
    with _isolated_test_profile(workspace=tmp_path) as profile:
        payload = AgentManager(profile, http_transport=transport).doctor(
            "endpoint-check", framework="crewai", model="fixture-chat-small"
        )

    assert payload["record_type"] == "agent_framework_doctor"
    assert payload["mutates"] is False
    assert payload["network_contacted"] is False
    assert payload["credential_behavior"] == "never reads or transmits credentials"
    assert payload["endpoint_probes"]["primary"]["attempted"] is False
    assert transport.requests == []
    assert payload["execution_boundary"]["starts_agents"] is False


def test_agent_doctor_probe_verifies_anonymous_models_response(tmp_path: Path, monkeypatch) -> None:
    transport = FakeHttpTransport({"data": [{"id": "provider-chat-small:8b"}]})
    monkeypatch.setattr(
        "aiplane.agents.framework_package_versions",
        lambda _framework: [
            {
                "requirement": "crewai",
                "distribution": "crewai",
                "installed": True,
                "version": "synthetic",
                "compatibility": "observed_only",
            }
        ],
    )
    with _isolated_test_profile(workspace=tmp_path) as profile:
        payload = AgentManager(profile, http_transport=transport).doctor(
            "endpoint-check", framework="crewai", model="fixture-chat-small", probe_endpoint=True
        )

    probe = payload["endpoint_probes"]["primary"]
    request, timeout = transport.requests[0]
    assert payload["network_contacted"] is True
    assert payload["ready"] is True
    assert probe["model_available"] is True
    assert request.full_url == "http://localhost:11434/v1/models"
    assert request.headers.get("Authorization") is None
    assert request.headers.get("X-api-key") is None
    assert timeout == 5


def test_agent_doctor_probe_reports_model_absence_and_stack_roles(tmp_path: Path, monkeypatch) -> None:
    manager, profile_context = _stack_bound_agent_manager(tmp_path)
    transport = FakeHttpTransport(
        {"data": [{"id": "provider-chat-small:8b"}]},
        {"data": [{"id": "provider-chat-small:8b"}]},
    )
    manager.http_transport = transport
    monkeypatch.setattr(
        "aiplane.agents.framework_package_versions",
        lambda _framework: [
            {
                "requirement": "langgraph",
                "distribution": "langgraph",
                "installed": True,
                "version": "synthetic",
                "compatibility": "observed_only",
            }
        ],
    )
    try:
        payload = manager.doctor("repository-review", stack="review_stack", probe_endpoint=True)
    finally:
        profile_context.__exit__(None, None, None)

    assert payload["ready"] is False
    assert set(payload["endpoint_probes"]) == {"planner", "reviewer"}
    assert payload["endpoint_probes"]["planner"]["model_available"] is True
    assert payload["endpoint_probes"]["reviewer"]["model_available"] is False
    assert len(transport.requests) == 2


def test_agent_doctor_cli_is_offline_without_probe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with _isolated_profiles_dir() as profiles_dir:
        result = run_cli(
            [
                "--profiles-dir",
                str(profiles_dir),
                "agents",
                "doctor",
                "endpoint-check",
                "--framework",
                "crewai",
                "--model",
                "fixture-chat-small",
            ]
        )

    payload = json.loads(result.stdout)
    assert result.code == 0
    assert payload["record_type"] == "agent_framework_doctor"
    assert payload["network_contacted"] is False
    assert payload["endpoint_probes"]["primary"]["attempted"] is False


def test_agent_doctor_validates_probe_timeout(tmp_path: Path) -> None:
    with _isolated_test_profile(workspace=tmp_path) as profile:
        with pytest.raises(ValueError, match="between 1 and 60"):
            AgentManager(profile).doctor("endpoint-check", model="fixture-chat-small", timeout_seconds=0)


def _stack_bound_agent_manager(tmp_path: Path) -> tuple[AgentManager, str]:
    profile = _isolated_test_profile(workspace=tmp_path)
    manager_context = profile
    loaded = manager_context.__enter__()
    exported = MachineManager(loaded).export_machine("local_box")
    machine_path = tmp_path / "local_box.machine.json"
    machine_path.write_text(json.dumps(exported), encoding="utf-8")
    MachineManager(loaded).import_file(machine_path)
    StackManager(loaded).setup(
        "review_stack",
        orchestrator="langgraph",
        runtime="ollama",
        model="fixture-chat-small",
        machine="local_box",
        access="same_host",
        endpoint="http://localhost:11434/v1",
        roles={"planner": "fixture-chat-small", "reviewer": "fixture-analysis-small"},
        limits={"timeout": "30m"},
        tools={"filesystem": "workspace_only"},
        approval_mode="ask",
        audit_label="review_stack",
    )
    return AgentManager(loaded), manager_context


def test_stack_bound_job_and_handoff_are_schema_valid_and_reproducible(tmp_path: Path) -> None:
    manager, profile_context = _stack_bound_agent_manager(tmp_path)
    try:
        job = manager.job(
            "repository-review",
            stack="review_stack",
            task="Review the current repository and propose a safe refactoring plan.",
            roles=["planner"],
        )
        handoff = manager.handoff(
            "repository-review",
            stack="review_stack",
            task="Review the current repository and propose a safe refactoring plan.",
            roles=["planner"],
        )
    finally:
        profile_context.__exit__(None, None, None)

    schema_root = Path(__file__).parents[1] / "schemas"
    Draft202012Validator(
        json.loads((schema_root / "aiplane-agent-job-v1.schema.json").read_text(encoding="utf-8"))
    ).validate(job)
    Draft202012Validator(
        json.loads((schema_root / "aiplane-agent-handoff-v1.schema.json").read_text(encoding="utf-8"))
    ).validate(handoff)
    assert job["target_roles"] == ["planner"]
    assert job["execution_boundary"]["runs_agents"] is False
    assert handoff["job"] == job
    assert handoff["checksums"]["environment_sha256"] == job["environment"]["sha256"]


def test_job_and_handoff_validation_detects_tampering_and_stays_workspace_bound(tmp_path: Path) -> None:
    manager, profile_context = _stack_bound_agent_manager(tmp_path)
    try:
        handoff = manager.handoff(
            "repository-review",
            stack="review_stack",
            task="Review the repository.",
        )
        path = tmp_path / "review.handoff.json"
        path.write_text(json.dumps(handoff), encoding="utf-8")
        assert manager.validate_job_file(path, handoff=True) == {
            "record_type": "agent_handoff_validation",
            "path": "review.handoff.json",
            "valid": True,
            "errors": [],
            "mutates": False,
        }

        handoff["job"]["task"] = "Tampered task"
        path.write_text(json.dumps(handoff), encoding="utf-8")
        invalid = manager.validate_job_file(path, handoff=True)
        assert invalid["valid"] is False
        assert "job checksum does not match" in invalid["errors"]

        handoff["job"]["environment"].pop("source_stack")
        path.write_text(json.dumps(handoff), encoding="utf-8")
        invalid_job_environment = manager.validate_job_file(path, handoff=True)
        assert invalid_job_environment["valid"] is False
        assert (
            "job: environment must identify name, profile, source_stack, orchestrator, and sha256"
            in invalid_job_environment["errors"]
        )

        handoff["environment"].pop("roles")
        path.write_text(json.dumps(handoff), encoding="utf-8")
        invalid_environment = manager.validate_job_file(path, handoff=True)
        assert invalid_environment["valid"] is False
        assert "environment: roles must be a non-empty object" in invalid_environment["errors"]

        outside = tmp_path.parent / "outside-agent-job.json"
        outside.write_text(json.dumps(handoff), encoding="utf-8")
        with pytest.raises(PermissionError, match="escapes workspace"):
            manager.validate_job_file(outside, handoff=True)
    finally:
        profile_context.__exit__(None, None, None)


def test_job_rejects_unknown_roles_unsafe_workspace_and_secret_like_task(tmp_path: Path) -> None:
    manager, profile_context = _stack_bound_agent_manager(tmp_path)
    try:
        with pytest.raises(ValueError, match="unknown stack roles"):
            manager.job("review", stack="review_stack", task="Review", roles=["missing"])
        with pytest.raises(ValueError, match="must not contain duplicates"):
            manager.job("review", stack="review_stack", task="Review", roles=["planner", "planner"])
        with pytest.raises(ValueError, match="safe relative path"):
            manager.job("review", stack="review_stack", task="Review", job_workspace="../outside")
        with pytest.raises(ValueError, match="secret-like"):
            manager.job("review", stack="review_stack", task="api_key=sk-abcdefghijklmnop")
    finally:
        profile_context.__exit__(None, None, None)


def test_agent_job_cli_renders_then_validates_workspace_artifact(tmp_path: Path) -> None:
    with _isolated_profiles_dir() as profiles_dir:
        profile = _load_profile_with_test_models("local-dev", tmp_path, profiles_dir=profiles_dir)
        exported = MachineManager(profile).export_machine("local_box")
        machine_path = tmp_path / "local_box.machine.json"
        machine_path.write_text(json.dumps(exported), encoding="utf-8")
        MachineManager(profile).import_file(machine_path)
        StackManager(profile).setup(
            "review_stack",
            orchestrator="langgraph",
            runtime="ollama",
            model="fixture-chat-small",
            machine="local_box",
            access="same_host",
            endpoint="http://localhost:11434/v1",
        )
        common = ["--workspace", str(tmp_path), "--profiles-dir", str(profiles_dir)]
        rendered = run_cli(
            [
                *common,
                "agents",
                "job",
                "render",
                "repository-review",
                "--stack",
                "review_stack",
                "--task",
                "Review the repository.",
            ]
        )
        assert rendered.code == 0
        payload = json.loads(rendered.stdout)
        assert payload["record_type"] == "agent_job"
        artifact = tmp_path / "review.job.json"
        artifact.write_text(rendered.stdout, encoding="utf-8")
        validated = run_cli([*common, "agents", "job", "validate", "review.job.json"])

    assert validated.code == 0
    assert json.loads(validated.stdout)["valid"] is True


def test_control_enforcement_reports_advisory_agent_controls() -> None:
    report = framework_control_enforcement(
        "langgraph",
        {
            "planner": {
                "tools": {"filesystem": "workspace_only", "shell": "guarded"},
                "limits": {"timeout": "30m", "max_tokens": 1000},
                "audit_label": "review.planner",
            }
        },
        "ask",
        job_workspace=True,
    )

    assert report["enforcement_ready"] is False
    assert set(report["requires_runtime_enforcement"]) == {
        "workspace_boundary",
        "tool_policy",
        "approval_mode",
        "limits",
        "audit_label",
    }
    assert report["controls"]["workspace_boundary"]["aiplane_status"] == "validated_in_handoff"
    assert report["controls"]["workspace_boundary"]["runtime_status"] == "not_enforced"
    assert report["controls"]["tool_policy"]["runtime_status"] == "not_enforced"


def test_manifest_job_and_stack_doctor_surface_control_enforcement(tmp_path: Path) -> None:
    manager, profile_context = _stack_bound_agent_manager(tmp_path)
    try:
        manifest = manager.manifest("repository-review", stack="review_stack")
        job = manager.job("repository-review", stack="review_stack", task="Review the repository.")
        doctor = StackManager(manager.profile).doctor("review_stack")
    finally:
        profile_context.__exit__(None, None, None)

    assert manifest["control_enforcement"]["controls"]["tool_policy"]["requested"] is True
    assert job["control_enforcement"]["controls"]["workspace_boundary"]["aiplane_status"] == "validated_in_handoff"
    check = next(item for item in doctor["checks"] if item["name"] == "agent_control_enforcement")
    assert check["warning"] is True
    assert check["controls"]["limits"]["runtime_status"] == "not_enforced"
