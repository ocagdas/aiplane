from __future__ import annotations

from pathlib import Path

import pytest

from aiplane.agent_frameworks import FRAMEWORK_SPECS, render_framework_starter
from aiplane.agents import AgentManager
from aiplane.config import parse_yaml
from tests.cli_fixtures import run_cli
from tests.profile_fixtures import _isolated_profiles_dir, _isolated_test_profile


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
        assert {"agent-environment.json", "agent-environment.yaml", "framework-config.yaml"} <= set(row["files"])
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
