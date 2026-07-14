from __future__ import annotations

from pathlib import Path
import re
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


PUBLIC_ONBOARDING_DOCS = (
    Path("README.md"),
    Path("docs/user/index.md"),
    Path("docs/user/README.md"),
    Path("docs/user/overview.md"),
)


def test_public_onboarding_uses_concrete_export_commands_and_nonempty_sections() -> None:
    for path in PUBLIC_ONBOARDING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*aiplane export\s*$", text), path
        assert "aiplane export continue" in text, path
        assert not re.search(r"(?m)^#{1,6} .+\n(?=#{1,6} )", text), path


def test_user_workflow_indexes_have_sequential_numbering() -> None:
    for path in (Path("docs/user/index.md"), Path("docs/user/README.md")):
        text = path.read_text(encoding="utf-8")
        expected_sections = (("Start here", [1, 2, 3, 4, 5]), ("Common workflows", [1, 2, 3, 4, 5]))
        for heading, expected in expected_sections:
            section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
            actual = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", section)]
            assert actual == expected, (path, heading, actual)


def test_public_onboarding_links_and_code_fences_are_valid() -> None:
    for path in PUBLIC_ONBOARDING_DOCS:
        text = path.read_text(encoding="utf-8")
        assert text.count("```") % 2 == 0, path
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            local_target = target.split("#", 1)[0]
            if not local_target or "://" in local_target or local_target.startswith("mailto:"):
                continue
            assert (path.parent / local_target).exists(), (path, target)


def test_public_positioning_agrees_across_metadata_and_launch_docs() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    description = project["project"]["description"].lower()
    assert "environment doctor" in description
    assert "configuration compiler" in description

    for path in (Path("README.md"), Path("docs/project/strategy.md"), Path("docs/project/public-launch-review.md")):
        opening = path.read_text(encoding="utf-8")[:2000].lower()
        assert "environment doctor" in opening, path
        assert "configuration compiler" in opening, path

    readme_opening = Path("README.md").read_text(encoding="utf-8")[:2000]
    assert "aiplane quickstart local-coding --dry-run" in readme_opening
    assert "First outcome:" in readme_opening

    readme = Path("README.md").read_text(encoding="utf-8")
    assert readme.index("## Core onboarding flow") < readme.index("## Advanced and experimental commands")
    readme_lower = readme.lower()
    for stale_breadth in (
        "control plane",
        "control-plane",
        "agentic environments",
        "provisioning and automation",
        "benchmark and evaluation",
        "machines and stacks",
        "mcp",
    ):
        assert stale_breadth not in readme_lower

    keywords = set(project["project"]["keywords"])
    assert {"environment", "configuration", "diagnostics", "reproducibility"} <= keywords
    assert keywords.isdisjoint({"mcp", "agents", "benchmarks", "stacks", "provisioning"})


def test_install_channels_and_release_workflows_are_explicit() -> None:
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    validator = Path("scripts/verify_install_channels.py").read_text(encoding="utf-8")
    setup = Path("docs/user/setup.md").read_text(encoding="utf-8")

    for os_runner in ("ubuntu-latest", "macos-14", "windows-latest"):
        assert os_runner in ci
    for channel in ("pip", "pipx", "uv"):
        assert f"def verify_{channel}" in validator
    assert "python scripts/verify_install_channels.py dist" in ci
    assert "tests/test_platform_support.py" in ci
    for portable_command in ("profiles", "hardware", "recommend", "policy", "integrations"):
        assert f'"{portable_command}"' in validator
    assert "unsupported_platform" in validator
    assert "tags:" in release and '- "v*"' in release
    assert 'tag == f"v{version}"' in release
    assert "gh release create" in release
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_init = Path("src/aiplane/__init__.py").read_text(encoding="utf-8")
    assert f'__version__ = "{project["project"]["version"]}"' in package_init
    assert {"Homepage", "Documentation", "Repository", "Issues"} <= set(project["project"]["urls"])
    assert "pypa/gh-action-pypi-publish" not in release
    for command in (
        "uv tool install",
        "pipx install",
        "python -m pip install",
        "uv tool uninstall",
        "pipx uninstall",
        "python -m pip uninstall",
    ):
        assert command in setup
    assert "Do not assume index publication" in setup


def test_public_workflow_and_terminology_do_not_regress_to_stale_promises() -> None:
    for path in (Path("docs/user/index.md"), Path("docs/user/README.md"), Path("docs/user/overview.md")):
        text = path.read_text(encoding="utf-8")
        assert "one exact next action" in text, path
        assert "prints the next" not in text, path

    for path in (
        Path("SECURITY.md"),
        Path("docs/project/integrations-roadmap.md"),
        Path("docs/user/machines-and-stacks.md"),
    ):
        assert "control-plane" not in path.read_text(encoding="utf-8").lower(), path


def test_p0_documentation_sweep_stays_open_until_user_demonstrations() -> None:
    backlog = Path("docs/project/product-adoption-backlog-2026-07.md").read_text(encoding="utf-8")

    assert "**P0 completion gate.**" in backlog
    assert "after P0 items 4-9 are complete" in backlog
    assert "must be repeated after the user-testing demonstrations" in backlog
    assert "interim pass does not close this gate" in backlog


def test_post_gate_backlog_numbers_are_sequential() -> None:
    backlog = Path("docs/project/product-adoption-backlog-2026-07.md").read_text(encoding="utf-8")
    numbered = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", backlog)]
    assert numbered == list(range(1, 25))
