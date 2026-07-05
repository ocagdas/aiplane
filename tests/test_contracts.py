from __future__ import annotations

from pathlib import Path

from aiplane.integration_contracts import ALL_INTEGRATION_TOOLS, required_roles
from aiplane.mcp import TOOL_SCHEMAS, mcp_manifest
from aiplane.model_resources import (
    accelerator_api_requirements,
    gpu_vendor_requirement,
    matches_accelerator_api_requirement,
    matches_gpu_vendor_requirement,
    parameter_billions,
    resource_guess,
)
from aiplane.runtime_catalog import (
    PROVIDER_ENDPOINT_DEFAULTS,
    RUNTIME_DEFINITIONS,
    SOURCE_DEFINITIONS,
)
from aiplane.runtime_pull import runtime_pull_support


def test_integration_contracts_define_tools_and_roles_once() -> None:
    assert "continue" in ALL_INTEGRATION_TOOLS
    assert "generic-mcp" in ALL_INTEGRATION_TOOLS
    assert [role["name"] for role in required_roles("continue")] == [
        "chat",
        "autocomplete",
        "embedding",
    ]
    assert required_roles("generic-mcp") == []


def test_model_resource_helpers_parse_and_match_requirements() -> None:
    assert parameter_billions("vendor/model-7b-q4") == 7.0
    assert parameter_billions("qwen2.5-14B-instruct") == 14.0
    assert resource_guess(9, ["chat"]) == (16, 32, 6, 10)

    model = {"gpu_vendor_requirement": "any", "accelerator_api_requirements": ["cuda"]}
    assert gpu_vendor_requirement(model) == "generic"
    assert accelerator_api_requirements(model) == ["cuda"]
    assert matches_gpu_vendor_requirement(model, "nvidia")
    assert matches_gpu_vendor_requirement(model, "generic")
    assert matches_accelerator_api_requirement(model, "cuda")
    assert not matches_accelerator_api_requirement(model, "generic")


def test_mcp_manifest_tools_have_input_schemas() -> None:
    names = {tool["name"] for tool in mcp_manifest()["tools"]}
    assert names <= set(TOOL_SCHEMAS)


def test_runtime_definition_reexports_keep_catalog_contracts_stable() -> None:
    assert RUNTIME_DEFINITIONS["ollama"]["model_sources"] == ["ollama", "gguf_import"]
    assert SOURCE_DEFINITIONS["huggingface_gguf"]["typical_runtimes"] == [
        "llamacpp",
        "localai",
        "ollama",
    ]
    assert PROVIDER_ENDPOINT_DEFAULTS["ollama"]["endpoint"] == "http://localhost:11434"


def test_runtime_pull_support_is_pure_and_source_based() -> None:
    assert runtime_pull_support(
        "ollama", {"provider": "llamacpp", "source": "huggingface_gguf"}
    )["supported"]
    unsupported = runtime_pull_support(
        "localai", {"provider": "llamacpp", "source": "huggingface_gguf"}
    )
    assert not unsupported["supported"]
    assert "manual" in unsupported["reason"]


def test_aiplane_skill_is_versioned_and_not_template_text() -> None:
    skill = Path("skills/aiplane/SKILL.md")
    text = skill.read_text(encoding="utf-8")
    assert "name: aiplane" in text
    assert "Version: 0.1.0" in text
    assert "TODO" not in text
    assert "control-plane CLI" in text
    assert Path("skills/aiplane/agents/openai.yaml").is_file()
