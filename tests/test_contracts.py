from __future__ import annotations

from pathlib import Path
import tomllib

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
    assert runtime_pull_support("ollama", {"provider": "llamacpp", "source": "huggingface_gguf"})["supported"]
    unsupported = runtime_pull_support("localai", {"provider": "llamacpp", "source": "huggingface_gguf"})
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


def test_cli_command_families_are_owned_outside_composition_root() -> None:
    root = Path("src/aiplane/cli.py").read_text(encoding="utf-8")
    for module in (
        "cli_public.py",
        "cli_execution.py",
        "cli_providers.py",
        "cli_runtimes.py",
        "cli_launch_support.py",
        "cli_profile_support.py",
        "cli_presenters.py",
        "cli_public_workflows.py",
    ):
        assert (Path("src/aiplane") / module).is_file()
    for command in ("discover", "quickstart", "run", "code", "providers", "runtimes"):
        assert f'if args.command == "{command}"' not in root
    assert len(root.splitlines()) < 500
    for helper in (
        "_launch_plan",
        "_validate_profile",
        "_AzCommandReporter",
        "_hardware_show_text",
        "_public_discover",
        "_bootstrap_local_profile",
        "_quickstart_local_coding",
    ):
        assert f"def {helper}" not in root
        assert f"class {helper}" not in root


def test_dev_dependencies_include_no_isolation_build_backend() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dev_dependencies = project["project"]["optional-dependencies"]["dev"]
    assert "setuptools==83.0.0" in dev_dependencies


def test_full_check_uses_configurable_file_level_parallelism() -> None:
    script = Path("scripts/check.sh").read_text(encoding="utf-8")
    assert "AIPLANE_TEST_WORKERS:-4" in script
    assert "--dist loadfile" in script


def test_external_io_calls_are_centralized_in_boundaries() -> None:
    violations = []
    for path in Path("src/aiplane").glob("*.py"):
        if path.name == "boundaries.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in ("subprocess.run(", "subprocess.Popen(", "urlopen("):
            if token in text:
                violations.append(f"{path}:{token}")
    assert violations == []
