from __future__ import annotations

from pathlib import Path
import re
import tomllib
import warnings

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
    line_count = len(root.splitlines())
    if line_count >= 500:
        warnings.warn(
            f"src/aiplane/cli.py has {line_count} lines; keep extracting command-family ownership before it reaches 600",
            stacklevel=1,
        )
    assert line_count < 600
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
    assert "after all numbered P0 work is complete" in backlog
    assert "must be repeated after the user-testing demonstrations" in backlog
    assert "interim pass does not close this gate" in backlog


def test_post_gate_backlog_numbers_are_sequential() -> None:
    backlog = Path("docs/project/product-adoption-backlog-2026-07.md").read_text(encoding="utf-8")
    numbered = [int(value) for value in re.findall(r"(?m)^(\d+)\. ", backlog)]
    assert numbered == list(range(1, 24))


def test_public_demo_plan_is_bounded_reproducible_and_uses_current_commands() -> None:
    text = Path("docs/project/public-demo-plan.md").read_text(encoding="utf-8")

    assert text.count("### Primary public adoption cut") == 1
    assert text.count("## P0 validation recording") == 2
    assert "one introductory product video" in text
    for command in (
        "aiplane quickstart local-coding --dry-run",
        "aiplane discover",
        "aiplane doctor",
        "aiplane recommend",
        "aiplane export continue",
        "aiplane profiles render local-dev",
        "aiplane profiles validate local-dev",
        "aiplane profiles repair local-dev --file models.yaml --dry-run",
        "aiplane hardware export-machine --name gpu-workstation",
        "aiplane machines import gpu-workstation.machine.yaml",
        "aiplane remote tunnel plan --target gpu_workstation_ssh",
    ):
        assert command in text

    assert "cmp demo-backup/local-dev.profile.json demo-backup/local-dev.restored.profile.json" in text
    assert "cannot reconstruct user customizations" in text
    assert "It does not start a process" in text
    assert "control plane" not in text.lower()
    assert "mvp_0." not in text


def test_install_verifier_is_portable_and_never_starts_supported_tunnels() -> None:
    verifier = Path("scripts/verify_install_channels.py").read_text(encoding="utf-8")

    assert "model_path.name" in verifier
    assert 'openai_config.get("model") != "portable-smoke.gguf"' in verifier
    assert 'cli("remote", "tunnel", "plan"' in verifier
    assert 'if system == "Windows":' in verifier
    assert 'if platform.system() in {"Darwin", "Windows"}:' not in verifier
    darwin_guard, windows_guard = verifier.split('if system == "Windows":', 1)
    assert '"tunnel",\n                "start"' not in darwin_guard
    assert '"tunnel",\n                "start"' in windows_guard


def test_backlog_review_reference_is_portable_and_gates_remain_open() -> None:
    backlog = Path("docs/project/product-adoption-backlog-2026-07.md").read_text(encoding="utf-8")

    assert "/home/" not in backlog
    assert Path("docs/project/reviews/dev-mvp-0.5-latest-review-evaluation.md").is_file()
    assert "**P0 completion gate.**" in backlog
    assert "independent users reproduce each" in backlog
    assert "must be repeated after the user-testing demonstrations" in backlog


def test_primary_adoption_cut_contains_only_the_core_command_story() -> None:
    text = Path("docs/project/public-demo-plan.md").read_text(encoding="utf-8")
    primary = text.split("### Primary public adoption cut", 1)[1].split("### P0 workflow-validation recordings", 1)[0]

    commands = re.findall(r"(?m)^aiplane .+$", primary)
    assert commands == [
        "aiplane quickstart local-coding --dry-run",
        "aiplane discover",
        "aiplane doctor",
        "aiplane recommend",
        "aiplane export continue",
    ]
    for advanced in (" chat ", " run ", " code ", " mcp ", " stacks ", " orchestrators ", " deploy ", " benchmarks "):
        assert advanced not in primary.lower()


def test_release_workflow_is_checksummed_versioned_and_quality_gated() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    setup = Path("docs/user/setup.md").read_text(encoding="utf-8")
    process = Path("docs/project/release-process.md").read_text(encoding="utf-8")

    assert "run: scripts/check.sh" in workflow
    assert "sha256sum aiplane-* > SHA256SUMS" in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert "Write generated release notes" in workflow
    assert "RELEASE_NOTES.md" in workflow
    assert "docs/project/releases" not in workflow
    assert "--notes-file RELEASE_NOTES.md" in workflow
    assert 'gh release create "${{ steps.tag.outputs.name }}"' in workflow
    for text in (setup, process):
        assert "SHA256SUMS" in text
        assert "rollback" in text.lower()


def test_ci_exposes_one_stable_release_gate_and_documents_hosted_protection() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    protection = Path("docs/project/repository-protection.md").read_text(encoding="utf-8")

    assert "  release-gate:" in workflow
    assert "needs: [checks, compatibility, install-channels]" in workflow
    assert "name: Release gate" in workflow
    assert "CI / Release gate" in protection
    assert "require pull requests" in protection
    assert "block force pushes" in protection
    assert "hosted state" in protection


def test_preview_scope_freeze_keeps_advanced_surface_out_of_public_promise() -> None:
    freeze = Path("docs/project/preview-scope-freeze.md").read_text(encoding="utf-8")
    coverage = Path("docs/project/command-coverage.md").read_text(encoding="utf-8")

    assert "Until the P0 gates close" in freeze
    assert "No new integration, runner, orchestrator, stack, benchmark, deployment, MCP-write capability" in freeze
    assert "## Exception process" in freeze
    assert "synchronized changes to strategy, roadmap, command coverage, help, and public documentation" in freeze
    assert "| Experimental |" in coverage


def test_every_demo_timeline_step_has_exact_commands_and_spoken_narration() -> None:
    text = Path("docs/project/public-demo-plan.md").read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^#{3,4} (\d:\d{2}-\d:\d{2}) — .+$", text))

    assert len(matches) == 16
    for index, match in enumerate(matches):
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else text.find("## Optional fourth video", match.end())
        )
        section = text[match.end() : end]
        assert "Exact command" in section, match.group(1)
        assert "Narration:" in section, match.group(1)
        assert "> " in section, match.group(1)


def test_successful_main_merge_versions_tags_and_uploads_a_bound_wheel() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    documentation = Path("docs/project/ci-wheel-artifacts.md").read_text(encoding="utf-8")

    assert "classify-main-push:" in workflow
    assert "github.event_name == 'push' && github.ref == 'refs/heads/main'" in workflow
    assert "Detect associated pull request" in workflow
    assert "AIPLANE_ASSOCIATED_PR" in workflow
    assert "python scripts/version.py classify-ci --github-output" in workflow
    assert "ci-version-bump-and-tag:" in workflow
    assert "needs.classify-main-push.outputs.mode == 'ci_patch_after_merge'" in workflow
    assert "python scripts/version.py set" in workflow
    assert "[skip ci-version]" in workflow
    assert "python scripts/version.py tag --ci-artifact" in workflow
    assert "git push origin HEAD:main" in workflow
    assert "git push origin" in workflow
    assert "direct-version-tag:" in workflow
    assert "needs.classify-main-push.outputs.mode == 'maintainer_direct_main_version_commit'" in workflow
    assert "main-versioned-wheel:" in workflow
    assert (
        "always() && (needs.ci-version-bump-and-tag.result == 'success' || needs.direct-version-tag.result == 'success')"
        in workflow
    )
    assert "python -m build --wheel --outdir artifacts" in workflow
    assert "python scripts/verify_install_channels.py artifacts --channel pip" in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    for workflow_text in (workflow, release):
        assert "uses: actions/checkout@v7" in workflow_text
        assert "uses: actions/setup-python@v6" in workflow_text
        assert "uses: actions/checkout@v4" not in workflow_text
        assert "uses: actions/setup-python@v5" not in workflow_text
    assert "uses: astral-sh/setup-uv@v8.3.2" in workflow
    assert "uses: astral-sh/setup-uv@v8.3.2" in release
    assert "uses: astral-sh/setup-uv@v6" not in workflow
    assert "uses: astral-sh/setup-uv@v6" not in release
    assert "uses: actions/upload-artifact@v7" in workflow
    assert "uses: actions/upload-artifact@v4" not in workflow
    assert "version_commit_short" in workflow
    assert "cut -c1-7" in workflow
    assert (
        "aiplane-wheel-v${{ steps.resolved.outputs.version }}-${{ steps.resolved.outputs.version_commit_short }}"
        in workflow
    )
    assert "aiplane-wheel-v${{ steps.resolved.outputs.version }}-${{ steps.resolved.outputs.tag }}" not in workflow
    assert (
        "aiplane-wheel-v${{ steps.resolved.outputs.version }}-${{ steps.resolved.outputs.version_commit }}"
        not in workflow
    )
    assert "retention-days: 30" in workflow
    assert "ci-artifact" in release
    assert "skipping public GitHub Release publication" in release
    assert "not immutable public releases" in documentation
